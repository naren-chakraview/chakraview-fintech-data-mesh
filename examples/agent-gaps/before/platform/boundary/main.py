"""Boundary HTTP service. Only the gateway reaches it; the gateway verifies the client certificate.

Run: uvicorn --factory boundary.main:get_app --app-dir platform
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from governance.enforce import OPAError as MaskingOPAError
from governance.enforce import elasticsearch_write_audit
from shared.governance.grants import GrantStore, MemoryGrantStore, PostgresGrantStore, utc_now
from shared.governance.products import load_products
from shared.identity import AuthError, Caller, CallerVerifier, JWKSCache

from .lineage_check import make_lineage_check
from .pipeline import Denied, Services, read_rows, read_sparql
from .policy import OPAError, decide, policy_revisions
from .reader import FixtureReader
from .sparql import UpstreamError

REPO_ROOT = Path(__file__).resolve().parents[2]


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
        )


class ReadBody(BaseModel):
    query: str


def create_app(settings: Settings, *, grants: Optional[GrantStore] = None,
               decide_fn=decide, audit=elasticsearch_write_audit,
               clock=utc_now, sparql_transport=None, jwks_fetch=None) -> FastAPI:
    products = load_products(settings.domains_dir)
    if grants is None:
        if settings.grant_store == "memory":
            grants = MemoryGrantStore()  # development only: grants do not survive a restart
        else:
            grants = PostgresGrantStore()

    services = Services(
        products=products,
        reader=FixtureReader(settings.fixtures_dir),
        grants=grants,
        decide=decide_fn,
        audit=audit,
        lineage_check=make_lineage_check(settings.lineage_dir, settings.lineage_trust_dir),
        revisions=policy_revisions(
            settings.policy_root,
            {pid: settings.policy_root / "domains" / p["domain"] / "policy" / f"{p['name']}.rego"
             for pid, p in products.items()},
        ),
        clock=clock,
        sparql_endpoints=settings.fuseki_endpoints,
        sparql_transport=sparql_transport,
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

    async def get_caller(request: Request) -> Caller:
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

    @app.get("/health")
    async def health():
        return {"status": "healthy", "products_loaded": len(products)}

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
