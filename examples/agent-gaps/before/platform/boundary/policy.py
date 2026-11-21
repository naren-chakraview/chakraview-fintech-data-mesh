"""OPA decisions for the boundary, and the policy revisions written to every audit record."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_OPA_DECISION_URL = "http://opa:8181/v1/data/data_mesh/access"


class OPAError(Exception):
    """OPA gave no valid decision. The caller must deny."""


@dataclass(frozen=True)
class Decision:
    allow: bool
    requires_approval: bool


async def decide(
    policy_input: dict,
    *,
    url: Optional[str] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Decision:
    """Evaluate data_mesh/access. Anything other than two booleans is an error, never a default.

    The URL is read from OPA_DECISION_URL at call time, so a process can point at its own OPA.
    """
    url = url or os.getenv("OPA_DECISION_URL", DEFAULT_OPA_DECISION_URL)
    try:
        async with httpx.AsyncClient(timeout=2.0, transport=transport) as client:
            response = await client.post(url, json={"input": policy_input})
    except httpx.HTTPError as exc:
        raise OPAError(f"OPA unreachable: {exc}") from exc

    if response.status_code != 200:
        raise OPAError(f"OPA returned HTTP {response.status_code}")
    try:
        result = response.json()["result"]
    except (ValueError, KeyError, TypeError) as exc:
        raise OPAError("OPA response has no result") from exc

    if not isinstance(result, dict) or not (
        isinstance(result.get("allow"), bool) and isinstance(result.get("requires_approval"), bool)
    ):
        raise OPAError("OPA decision is malformed")
    return Decision(allow=result["allow"], requires_approval=result["requires_approval"])


def _sha256_files(paths) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(Path(path).name).encode())
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def policy_revisions(policy_root: Path, product_policy_files: dict) -> dict:
    """Content hashes of the platform guardrails and each product's domain policy.

    Changing any rule changes the revision, so an audit record names the exact rules that decided it.
    """
    root = Path(policy_root)
    platform_files = [
        path for path in (root / "platform/governance/opa-policies").glob("*.rego")
        if not path.name.endswith("_test.rego")
    ]
    return {
        "platform": _sha256_files(platform_files),
        "domains": {
            product_id: _sha256_files([path]) if path.exists() else "missing"
            for product_id, path in product_policy_files.items()
        },
    }
