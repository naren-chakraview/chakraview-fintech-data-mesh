import os
from typing import Optional

import httpx

OPA_URL = os.getenv("OPA_URL", "http://opa:8181/v1/data/data_mesh/access")

# Lowest to highest sensitivity; a product is classified by its most sensitive column.
CLASSIFICATION_ORDER = ["public", "sensitive", "confidential", "pii", "restricted"]


class OPAError(Exception):
    """OPA gave no valid decision; the caller must deny the request."""


async def evaluate_access(
    user_id: str,
    user_role: str,
    action: str,
    data_classification: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> dict:
    """Ask OPA for an access decision. Raises OPAError on any failure."""
    payload = {
        "input": {
            "user_id": user_id,
            "user_role": user_role,
            "action": action,
            "data_classification": data_classification,
        }
    }
    try:
        async with httpx.AsyncClient(timeout=2.0, transport=transport) as client:
            response = await client.post(OPA_URL, json=payload)
    except httpx.HTTPError as exc:
        raise OPAError(f"OPA unreachable: {exc}") from exc

    if response.status_code != 200:
        raise OPAError(f"OPA returned HTTP {response.status_code}")

    try:
        result = response.json()["result"]
    except (ValueError, KeyError, TypeError) as exc:
        raise OPAError("OPA response has no result") from exc

    if not isinstance(result, dict) or not (
        isinstance(result.get("allow"), bool)
        and isinstance(result.get("requires_approval"), bool)
    ):
        raise OPAError("OPA decision is malformed")

    return {"allow": result["allow"], "requires_approval": result["requires_approval"]}


def product_classification(product: dict) -> str:
    """Highest column classification; restricted when there are no columns or a value is unknown."""
    columns = (product.get("access_policy") or {}).get("columns") or []
    levels = [column.get("classification") for column in columns]
    if not levels or any(level not in CLASSIFICATION_ORDER for level in levels):
        return "restricted"
    return max(levels, key=CLASSIFICATION_ORDER.index)
