"""Boundary HTTP service. Only the gateway reaches it; the gateway verifies the client certificate.

Run: uvicorn --factory boundary.main:get_app --app-dir platform
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from governance.enforce import OPAError as MaskingOPAError
from governance.enforce import elasticsearch_write_audit
from shared.governance.grants import GrantStore, MemoryGrantStore, PostgresGrantStore, utc_now
from shared.governance.products import load_products
from shared.identity import AuthError, Caller, CallerVerifier, JWKSCache
from shared.identity import Principal
from delegation import DelegationError, GatewayTrust, JtiCache, load_gateway_trusts, verify_forwarded
from proposals.payload import PayloadError
from proposals.writer import GovernedWriter, ProposalConflict, ProposalNotFound

from . import consent
from . import direct_writes
from . import writes as write_contracts

from . import proposals as governed
from .ledger import ReadLedger
from .lineage_check import make_lineage_check
from .pipeline import Denied, Services, read_aggregate, read_rows, read_sparql
from .policy import OPAError, decide, policy_revisions
from .reader import FixtureReader
from .sparql import UpstreamError

REPO_ROOT = Path(__file__).resolve().parents[2]
LOOPBACK_HOST = "127.0.0.1"
PRODUCT_WITH_PROPOSALS = "risk-compliance.risk-review-notes"
WRITER_SPIFFE_ID = "spiffe://chakracommerce.com/ns/boundary/sa/governed-writer"
WRITER_KEYID = "governed-writer"


@dataclass(frozen=True)
class Settings:
    domains_dir: Path
    fixtures_dir: Path
    lineage_dir: Path
    lineage_trust_dir: Path
    policy_root: Path
    idp_jwks_url: str
    idp_issuer: str
    idp_audience: str
    fuseki_endpoints: dict
    grant_store: str
    delegation_trust_dir: Path
    proposal_state_dir: Path
    writer_key_path: Path
    boundary_spiffe_id: str
    loopback_port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            domains_dir=Path(os.getenv("DOMAINS_DIR", REPO_ROOT / "domains")),
            fixtures_dir=Path(os.getenv("FIXTURES_DIR", REPO_ROOT / "platform/boundary/fixtures")),
            lineage_dir=Path(os.getenv("LINEAGE_DIR", REPO_ROOT / "platform/lineage/attestations")),
            lineage_trust_dir=Path(os.getenv("LINEAGE_TRUST_DIR", REPO_ROOT / "platform/lineage/trust-config")),
            policy_root=Path(os.getenv("POLICY_ROOT", REPO_ROOT)),
            idp_jwks_url=os.getenv("IDP_JWKS_URL", "http://dev-idp:8090/.well-known/jwks.json"),
            idp_issuer=os.getenv("IDP_ISSUER", "http://dev-idp:8090"),
            idp_audience=os.getenv("IDP_AUDIENCE", "data-mesh"),
            fuseki_endpoints=json.loads(os.getenv(
                "FUSEKI_ENDPOINTS",
                '{"risk-compliance": "http://risk-compliance-fuseki:3030/risk_compliance/sparql"}',
            )),
            grant_store=os.getenv("GRANT_STORE", "postgres"),
            delegation_trust_dir=Path(os.getenv("DELEGATION_TRUST_DIR", REPO_ROOT / "platform/delegation/trust-config")),
            proposal_state_dir=Path(os.getenv("PROPOSAL_STATE_DIR", REPO_ROOT / "platform/proposals/state")),
            writer_key_path=Path(os.getenv("PROPOSAL_SIGNING_KEY", REPO_ROOT / "platform/lineage/keys/governed-writer.key")),
            boundary_spiffe_id=os.getenv("BOUNDARY_SPIFFE_ID", "spiffe://chakracommerce.com/ns/boundary/sa/boundary"),
            loopback_port=int(os.getenv("LOOPBACK_PORT", "8080")),
        )


class ReadBody(BaseModel):
    query: str


class ProposalBody(BaseModel):
    format: str = "turtle"
    payload: str
    derived_from: List[str] = []


class DecisionBody(BaseModel):
    reason: str = ""


class WriteBody(BaseModel):
    rows: List[dict]
    derived_from: List[str] = []
    kind: Optional[str] = None  # captured | derived; defaults to the product's kind


def build_writer(settings: Settings, clock, *, product_id: str = PRODUCT_WITH_PROPOSALS) -> Optional[GovernedWriter]:
    """The governed writer for the review-notes product, or None when its signing key is not provisioned."""
    if not settings.writer_key_path.exists():
        return None
    return GovernedWriter(
        product_id=product_id,
        snapshot_dir=settings.fixtures_dir,
        attestation_dir=settings.lineage_dir,
        history_dir=settings.proposal_state_dir / "history",
        private_key_pem=settings.writer_key_path.read_bytes(),
        keyid=WRITER_KEYID,
        producer_spiffe_id=WRITER_SPIFFE_ID,
        clock=clock,
    )


def build_direct_writers(settings: Settings, clock, products: dict) -> dict:
    """A governed writer for each product that takes direct writes (addendum W1). Each one's current snapshot is kept
    in the state directory, never in the tracked fixtures, and starts from the product's fixture (empty for the new
    products). The review-notes writer is built by build_writer, since its snapshot is the tracked fixture."""
    if not settings.writer_key_path.exists():
        return {}
    writers = {}
    for product_id, product in products.items():
        if "write_kind" not in product or product_id == PRODUCT_WITH_PROPOSALS:
            continue
        fixture = settings.fixtures_dir / f"{product_id}.json"
        if not fixture.exists():
            continue
        columns = json.loads(fixture.read_text())["columns"]
        writers[product_id] = GovernedWriter(
            product_id=product_id,
            snapshot_dir=settings.proposal_state_dir / "products",
            attestation_dir=settings.lineage_dir,
            history_dir=settings.proposal_state_dir / "history",
            private_key_pem=settings.writer_key_path.read_bytes(),
            keyid=WRITER_KEYID,
            producer_spiffe_id=WRITER_SPIFFE_ID,
            clock=clock,
            columns=columns,
            seed_dir=settings.fixtures_dir,
        )
    return writers


def create_app(settings: Settings, *, grants: Optional[GrantStore] = None,
               decide_fn=decide, audit=elasticsearch_write_audit,
               clock=utc_now, sparql_transport=None, jwks_fetch=None,
               gateway_trusts: Optional[List[GatewayTrust]] = None, writer: Optional[GovernedWriter] = None,
               writers: Optional[dict] = None, limits: Optional[governed.Limits] = None) -> FastAPI:
    products = load_products(settings.domains_dir)
    if gateway_trusts is None:
        gateways_file = settings.delegation_trust_dir / "gateways.json"
        gateway_trusts = load_gateway_trusts(gateways_file) if gateways_file.exists() else []
    jti_cache = JtiCache()
    if writer is None:
        writer = build_writer(settings, clock)
    writers = dict(writers or {})
    if writer is not None:
        writers[writer.product_id] = writer
    for product_id, direct in build_direct_writers(settings, clock, products).items():
        writers.setdefault(product_id, direct)
    limits = limits or governed.Limits()
    ledger = ReadLedger()
    if grants is None:
        if settings.grant_store == "memory":
            grants = MemoryGrantStore()  # development only: grants do not survive a restart
        else:
            grants = PostgresGrantStore()

    async def audited(record: dict) -> None:
        # The boundary's own ledger learns a read only after its audit record is durably written.
        await audit(record)
        ledger.observe(record)

    services = Services(
        products=products,
        reader=FixtureReader(settings.fixtures_dir, settings.proposal_state_dir / "products"),
        grants=grants,
        decide=decide_fn,
        audit=audited,
        lineage_check=make_lineage_check(settings.lineage_dir, settings.lineage_trust_dir),
        revisions=policy_revisions(
            settings.policy_root,
            {pid: settings.policy_root / "domains" / p["domain"] / "policy" / f"{p['name']}.rego"
             for pid, p in products.items()},
        ),
        clock=clock,
        sparql_endpoints=settings.fuseki_endpoints,
        sparql_transport=sparql_transport,
        ledger=ledger,
    )
    cache_args = {"fetch": jwks_fetch} if jwks_fetch is not None else {}
    verifier = CallerVerifier(
        jwks=JWKSCache(settings.idp_jwks_url, **cache_args),
        issuer=settings.idp_issuer,
        audience=settings.idp_audience,
    )

    app = FastAPI(title="Data Boundary", version="1.0.0")
    app.state.services = services
    app.state.verifier = verifier

    def _on_loopback(request: Request) -> bool:
        server = request.scope.get("server")
        return bool(server) and server[0] == LOOPBACK_HOST and server[1] == settings.loopback_port

    def _forwarded_caller(request: Request) -> Caller:
        """A delegated call from the boundary's own sidecar, on the loopback listener only."""
        token = request.headers.get("x-zt-verified-token", "")
        if not token:
            raise HTTPException(status_code=401, detail="no delegated token on the loopback listener")
        try:
            delegation = verify_forwarded(token, gateway_trusts, audience=settings.boundary_spiffe_id,
                                          now=clock(), headers=request.headers)
            jti_cache.record(delegation.token_id, delegation.expires_at, clock())
        except DelegationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        principal = Principal(subject=delegation.user, roles=delegation.roles, claims={})
        return Caller(principal=principal, spiffe_id=delegation.actor, delegation=delegation)

    async def get_caller(request: Request) -> Caller:
        # The two listeners are different kinds of caller. Only the loopback listener, which only the boundary's own
        # sidecar can reach, takes delegated calls. On the mTLS listener the X-ZT-* headers are never read, so a
        # client cannot make a call look delegated by sending them.
        if _on_loopback(request):
            return _forwarded_caller(request)
        try:
            return await verifier.verify(request.headers)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="identity provider unavailable") from exc

    def purpose_or_400(purpose: str) -> str:
        if not purpose:
            raise HTTPException(status_code=400, detail="purpose is required")
        return purpose

    def handle(exc: Exception) -> HTTPException:
        if isinstance(exc, Denied):
            return HTTPException(status_code=exc.status, detail=exc.detail)
        if isinstance(exc, (OPAError, MaskingOPAError, UpstreamError)):
            return HTTPException(status_code=503, detail="dependency unavailable; no data returned")
        return HTTPException(status_code=503, detail="audit or grant store unavailable; no data returned")

    async def _governed(coro):
        try:
            return await coro
        except (Denied, PayloadError) as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        except ProposalConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProposalNotFound as exc:
            raise HTTPException(status_code=404, detail="proposal not found") from exc
        except write_contracts.WriteContractError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except write_contracts.WriteConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:  # any failure leaves the product unchanged and says so
            raise handle(exc) from exc

    def _writer_for(product_id: str) -> GovernedWriter:
        if writer is None or product_id != writer.product_id:
            raise HTTPException(status_code=404, detail="this product takes no proposals")
        return writer

    def _any_writer_for(product_id: str) -> GovernedWriter:
        target = writers.get(product_id)
        if target is None:
            raise HTTPException(status_code=404, detail="this product takes no writes")
        return target

    @app.get("/health")
    async def health():
        return {"status": "healthy", "products_loaded": len(products)}

    @app.post("/products/{product_id}/proposals", status_code=201)
    async def post_proposal(product_id: str, body: ProposalBody, caller: Caller = Depends(get_caller)):
        target = _writer_for(product_id)
        return await _governed(governed.propose(services, target, limits, caller, product_id,
                                                body.payload.encode("utf-8"), body.format, body.derived_from))

    @app.get("/products/{product_id}/proposals/{proposal_id}")
    async def get_proposal(product_id: str, proposal_id: str, caller: Caller = Depends(get_caller)):
        target = _writer_for(product_id)
        try:
            record = target.get(proposal_id)
        except ProposalNotFound as exc:
            raise HTTPException(status_code=404, detail="proposal not found") from exc
        owner = caller.delegation is None and "data_owner" in caller.principal.roles
        if caller.principal.subject != record["on_behalf_of"] and not owner:
            raise HTTPException(status_code=403, detail="only the person it acts for, or the owner, may read a proposal")
        return target.view(record)

    @app.post("/products/{product_id}/proposals/{proposal_id}/accept")
    async def accept_proposal(product_id: str, proposal_id: str, caller: Caller = Depends(get_caller)):
        target = _writer_for(product_id)
        return await _governed(governed.decide(services, target, caller, product_id, proposal_id, "accept"))

    @app.post("/products/{product_id}/proposals/{proposal_id}/reject")
    async def reject_proposal(product_id: str, proposal_id: str, body: DecisionBody,
                              caller: Caller = Depends(get_caller)):
        target = _writer_for(product_id)
        return await _governed(governed.decide(services, target, caller, product_id, proposal_id, "reject",
                                               body.reason))

    @app.post("/products/{product_id}/rollback")
    async def rollback_product(product_id: str, body: DecisionBody, caller: Caller = Depends(get_caller)):
        target = _any_writer_for(product_id)
        return await _governed(governed.rollback(services, target, caller, product_id, body.reason))

    @app.post("/products/{product_id}/writes", status_code=201)
    async def post_write(product_id: str, body: WriteBody, caller: Caller = Depends(get_caller)):
        target = _any_writer_for(product_id)
        return await _governed(direct_writes.direct_write(services, target, limits, caller, product_id,
                                                          body.rows, body.derived_from, body.kind))

    # Subject consent (addendum 2, W7): an agent proposes a value the customer decides on; only she accepts or declines.
    @app.post("/products/{product_id}/consent-proposals", status_code=201)
    async def post_consent_proposal(product_id: str, body: WriteBody, caller: Caller = Depends(get_caller)):
        target = _any_writer_for(product_id)
        return await _governed(consent.propose_consent(services, target, limits, caller, product_id,
                                                       body.rows, body.derived_from))

    @app.get("/products/{product_id}/consent-proposals/{proposal_id}")
    async def get_consent_proposal(product_id: str, proposal_id: str, caller: Caller = Depends(get_caller)):
        target = _any_writer_for(product_id)
        try:
            record = target.get(proposal_id)
        except ProposalNotFound as exc:
            raise HTTPException(status_code=404, detail="proposal not found") from exc
        if caller.delegation is not None or consent._subject_of(caller) != record.get("subject"):
            raise HTTPException(status_code=403, detail="only the data subject sees her own consent proposal")
        return consent._view(record)

    @app.post("/products/{product_id}/consent-proposals/{proposal_id}/accept")
    async def accept_consent_proposal(product_id: str, proposal_id: str, caller: Caller = Depends(get_caller)):
        target = _any_writer_for(product_id)
        return await _governed(consent.decide_consent(services, target, caller, product_id, proposal_id, "accept"))

    @app.post("/products/{product_id}/consent-proposals/{proposal_id}/decline")
    async def decline_consent_proposal(product_id: str, proposal_id: str, body: DecisionBody,
                                       caller: Caller = Depends(get_caller)):
        target = _any_writer_for(product_id)
        return await _governed(consent.decide_consent(services, target, caller, product_id, proposal_id, "decline",
                                                      body.reason))

    @app.get("/products/{product_id}/rows")
    async def get_rows(
        product_id: str,
        caller: Caller = Depends(get_caller),
        columns: str = Query(..., description="comma-separated column names"),
        purpose: str = Query(""),
    ):
        requested = [c for c in columns.split(",") if c]
        purpose_or_400(purpose)
        try:
            return await read_rows(services, caller, product_id, requested, purpose)
        except Denied as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        except Exception as exc:  # any failure on the read path denies; never return partial rows
            raise handle(exc) from exc

    @app.get("/products/{product_id}/aggregates")
    async def get_aggregates(
        product_id: str,
        caller: Caller = Depends(get_caller),
        group_by: str = Query(..., description="one public column"),
        purpose: str = Query(""),
    ):
        purpose_or_400(purpose)
        try:
            return await read_aggregate(services, caller, product_id, group_by, purpose)
        except Denied as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        except Exception as exc:
            raise handle(exc) from exc

    @app.post("/products/{product_id}/sparql")
    async def post_sparql(
        product_id: str,
        body: ReadBody,
        caller: Caller = Depends(get_caller),
        purpose: str = Query(""),
    ):
        purpose_or_400(purpose)
        try:
            return await read_sparql(services, caller, product_id, body.query, purpose)
        except Denied as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        except Exception as exc:
            raise handle(exc) from exc

    return app


def get_app() -> FastAPI:
    """Application factory for `uvicorn --factory boundary.main:get_app --app-dir platform`."""
    return create_app(Settings.from_env())
