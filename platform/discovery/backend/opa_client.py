"""Discovery's access decisions come from the same OPA decision the boundary uses."""

import sys
from pathlib import Path
from typing import Optional

import httpx

from shared.governance.products import product_classification, product_policy_input  # noqa: F401
from shared.identity import Caller

# The boundary's OPA client lives in platform/boundary, imported as the `boundary` package.
_PLATFORM = Path(__file__).resolve().parents[2]
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from boundary.policy import Decision, OPAError, decide  # noqa: E402

__all__ = ["Decision", "OPAError", "evaluate_access", "product_classification"]


async def evaluate_access(
    caller: Caller,
    product: dict,
    action: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Decision:
    """Ask OPA for an access decision for a verified caller. Raises OPAError on any failure."""
    policy_input = {
        "action": action,
        "principal": {"subject": caller.principal.subject, "roles": sorted(caller.principal.roles)},
        "workload": {"spiffe_id": caller.spiffe_id},
        "product": product_policy_input(product),
    }
    kwargs = {"transport": transport} if transport is not None else {}
    return await decide(policy_input, **kwargs)
