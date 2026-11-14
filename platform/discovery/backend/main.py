import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request

from shared.utils import get_logger
from shared.governance.grants import GrantStore, PostgresGrantStore, utc_now
from shared.governance.products import load_products
from shared.identity import AuthError, Caller, CallerVerifier, JWKSCache
from .models import AccessRequest, DataProductSearchResult
from .opa_client import OPAError, evaluate_access

logger = get_logger(__name__)

app = FastAPI(
    title="Data Mesh Discovery Portal",
    description="Self-service discovery and access management for data products",
    version="1.0.0",
)

REPO_ROOT = Path(__file__).resolve().parents[3]
IDENTITY_FIELDS = {"user_id", "user_role"}

# Demo storage. Products come from YAML; requests are in memory; grants are stored in Postgres.
data_products: dict = {}
access_requests: dict = {}
verifier: Optional[CallerVerifier] = None
grants: Optional[GrantStore] = None
clock = utc_now


def configure(*, caller_verifier: CallerVerifier, grant_store: GrantStore) -> None:
    """Set the identity verifier and grant store. Tests and the demos call this before the first request."""
    global verifier, grants
    verifier = caller_verifier
    grants = grant_store


def load_data_products():
    """Load data products from YAML files"""
    domains_path = Path(os.getenv("DOMAINS_DIR", REPO_ROOT / "domains"))
    loaded = load_products(domains_path)
    data_products.clear()
    data_products.update(loaded)
    for product_id in loaded:
        logger.info("Loaded data product", context={"product_id": product_id})


@app.on_event("startup")
async def startup():
    """Load data products and wire identity and grants from the environment"""
    global verifier, grants
    load_data_products()
    if verifier is None:
        verifier = CallerVerifier(
            jwks=JWKSCache(os.getenv("IDP_JWKS_URL", "http://dev-idp:8090/.well-known/jwks.json")),
            issuer=os.getenv("IDP_ISSUER", "http://dev-idp:8090"),
            audience=os.getenv("IDP_AUDIENCE", "data-mesh"),
        )
    if grants is None:
        grants = PostgresGrantStore()
    logger.info("Discovery portal started", context={"products_loaded": len(data_products)})


async def get_caller(request: Request) -> Caller:
    try:
        return await verifier.verify(request.headers)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="identity provider unavailable") from exc


@app.get("/api/products", response_model=List[DataProductSearchResult])
async def search_products(
    query: Optional[str] = Query(None, description="Search by name, domain, or tags"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
) -> List[DataProductSearchResult]:
    """Search for data products"""
    results = []

    for product_id, product_data in data_products.items():
        if domain and product_data.get("domain") != domain:
            continue

        if tag and tag not in product_data.get("tags", []):
            continue

        if query:
            query_lower = query.lower()
            searchable = (
                product_data.get("name", "").lower()
                + " " + product_data.get("domain", "").lower()
                + " " + " ".join(product_data.get("tags", []))
            )
            if query_lower not in searchable:
                continue

        results.append(
            DataProductSearchResult(
                id=product_id,
                name=product_data.get("name"),
                domain=product_data.get("domain"),
                owner=product_data.get("owner"),
                description=product_data.get("description", ""),
                tags=product_data.get("tags", []),
                freshness_minutes=product_data.get("sla", {}).get("freshness", {}).get("value", 0),
            )
        )

    logger.info(
        "Product search executed",
        context={"query": query, "results": len(results)},
    )
    return results


@app.get("/api/products/{product_id}")
async def get_product(product_id: str) -> dict:
    """Get detailed product information"""
    if product_id not in data_products:
        raise HTTPException(status_code=404, detail="Product not found")

    product = data_products[product_id]
    logger.info(
        "Product details retrieved",
        context={"product_id": product_id},
    )
    return product


@app.post("/api/access-requests")
async def request_access(request: Request, caller: Caller = Depends(get_caller)) -> dict:
    """Submit an access request. The subject and role come from the verified token, not the body."""
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    sent = IDENTITY_FIELDS & set(body)
    if sent:
        raise HTTPException(
            status_code=400,
            detail=f"identity comes from the verified token; remove: {', '.join(sorted(sent))}",
        )
    try:
        access = AccessRequest(**body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    product = data_products.get(access.data_product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    request_id = f"req_{len(access_requests) + 1}"
    now = clock()

    try:
        decision = await evaluate_access(caller, product, "request_access")
    except OPAError:
        access_requests[request_id] = _stored(request_id, caller, access, now, "denied")
        raise HTTPException(status_code=503, detail="Policy engine unavailable; request denied")

    approved = decision.allow and not decision.requires_approval
    status = "approved" if approved else "pending"

    response = {"id": request_id, "status": status}
    if status == "approved":
        response["message"] = "Access granted"
    else:
        response["message"] = "Access request submitted for review"
        response["routed_to"] = product["owner"]
        response["approval_sla_hours"] = product["access_policy"].get("approval_sla_hours", 4)

    access_requests[request_id] = _stored(request_id, caller, access, now, status)
    logger.info(
        "Access request evaluated",
        context={
            "request_id": request_id,
            "product_id": access.data_product_id,
            "subject": caller.principal.subject,
            "status": status,
        },
    )
    return response


def _stored(request_id: str, caller: Caller, access: AccessRequest, now, status: str) -> dict:
    return {
        "id": request_id,
        "subject": caller.principal.subject,
        "workload_spiffe_id": caller.spiffe_id,
        "data_product_id": access.data_product_id,
        "action": access.action,
        "justification": access.justification,
        "purpose": access.purpose or access.justification,
        "requested_columns": access.requested_columns,
        "requested_at": now.isoformat(),
        "status": status,
        "grant_id": None,
    }


@app.post("/api/access-requests/{request_id}/approve")
async def approve_access(
    request_id: str,
    caller: Caller = Depends(get_caller),
    ttl_days: int = Query(1, ge=1, le=30, description="grant lifetime in days"),
) -> dict:
    """Approve a request as the product's owner. Creates a stored, expiring, scoped grant.

    The approver must own the product: the owner name must appear in the token's `owns` claim.
    Approval is refused after the product's approval_sla_hours window.
    """
    stored = access_requests.get(request_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if stored["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"request is {stored['status']}")

    product = data_products[stored["data_product_id"]]
    if product["owner"] not in set(caller.principal.claims.get("owns", [])):
        raise HTTPException(status_code=403, detail="only the product owner can approve")

    now = clock()
    sla = timedelta(hours=int(product["access_policy"].get("approval_sla_hours", 4)))
    requested_at = datetime_from_iso(stored["requested_at"])
    if now - requested_at > sla:
        raise HTTPException(status_code=409, detail="approval window has closed")

    if not stored["requested_columns"]:
        raise HTTPException(status_code=409, detail="request names no columns to grant")

    grant = grants.create(
        subject=stored["subject"],
        workload_spiffe_id=stored["workload_spiffe_id"],
        product_id=stored["data_product_id"],
        columns=stored["requested_columns"],
        purpose=stored["purpose"],
        expires_at=now + timedelta(days=ttl_days),
    )
    stored["status"] = "approved"
    stored["grant_id"] = grant.id
    stored["approved_by"] = caller.principal.subject
    logger.info("Grant created", context={"grant_id": grant.id, "request_id": request_id})
    return {"request_id": request_id, "grant": grant.to_dict()}


def datetime_from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


@app.get("/api/access-requests/{request_id}")
async def get_access_request(request_id: str) -> dict:
    """Get access request status"""
    if request_id not in access_requests:
        raise HTTPException(status_code=404, detail="Request not found")

    return access_requests[request_id]


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "products_loaded": len(data_products),
        "pending_requests": len([
            r for r in access_requests.values()
            if r.get("status") == "pending"
        ]),
    }
