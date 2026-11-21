"""Container entry point for the scripted risk-review agent in the compose stack.

The agent holds no credential of its own. It is given the analyst's IdP token (the consent stand-in, documented),
and each call goes through the agent's sidecar, which issues a fresh delegated token. See channels.py.

Environment (set in docker-compose.yml):
  ANALYST_TOKEN_URL   the dev IdP's token endpoint for the analyst (the consent stand-in)
  IDP_ISSUER          the IdP's iss, which the sidecar must trust for the edge mint
  ADMIN_URL           the agent sidecar's admin listener, on the shared loopback
  BOUNDARY_URL        the boundary's sidecar, over mTLS
  AGENT_SPIFFE_ID, BOUNDARY_SPIFFE_ID
  CLIENT_CERT, CLIENT_KEY, CA_CERT   the agent's certificate and the dev CA
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from agent import RiskReviewAgent  # noqa: E402
from channels import HttpChannel  # noqa: E402


def analyst_token(url: str) -> str:
    response = httpx.post(url, timeout=10)
    response.raise_for_status()
    return response.json()["access_token"]


def wait_for_sidecar(channel: HttpChannel, attempts: int = 60) -> None:
    """The agent's sidecar starts beside the agent. Wait until its admin answers an edge mint."""
    last = None
    for _ in range(attempts):
        try:
            channel._delegated_token()
            return
        except (httpx.HTTPError, KeyError) as exc:
            last = exc
            time.sleep(1)
    raise SystemExit(f"the agent's sidecar did not come up: {last}")


def main() -> None:
    channel = HttpChannel(
        admin_url=os.environ["ADMIN_URL"],
        boundary_url=os.environ["BOUNDARY_URL"],
        idp_url=os.environ["ANALYST_TOKEN_URL"],
        idp_issuer=os.environ["IDP_ISSUER"],
        agent_spiffe_id=os.environ["AGENT_SPIFFE_ID"],
        boundary_spiffe_id=os.environ["BOUNDARY_SPIFFE_ID"],
        cert=(os.environ["CLIENT_CERT"], os.environ["CLIENT_KEY"]),
        ca=os.environ["CA_CERT"],
        user_token=analyst_token(os.environ["ANALYST_TOKEN_URL"]),
    )
    wait_for_sidecar(channel)
    result = RiskReviewAgent(channel, now=lambda: datetime.now(timezone.utc)).run()
    print(json.dumps({
        "snapshot_sha256": result.snapshot_sha256,
        "high_risk_stale": len(result.high_risk_stale),
        "proposals": [{"id": p["id"], "status": p["status"]} for p in result.proposals],
        "refusals": result.refusals,
    }, indent=2))


if __name__ == "__main__":
    main()
