"""The risk-review agent: a scripted, deterministic workload that acts for a risk analyst.

It is not an LLM, on purpose. The demos must be reproducible, and the claim under test is the governance,
which does not depend on how the agent decides. Given the same snapshot and the same clock, it proposes the
same notes every time. Its decisions are simple and written down here:

  1. It reads the shared core's version from semantics/core/fintech-core.ttl and requires 1.0.0.
  2. It reads the risk scores through the boundary (customer IRI, risk band, score date) and keeps the snapshot
     digest the boundary returns, because a proposal must cite the snapshot it was derived from.
  3. A customer is high-risk when the band is "high". A score is stale when it is older than the threshold.
  4. For each high-risk customer with a stale score, it proposes one review note.

It holds no credential of its own. It makes every call through a channel (channels.py), which gives each call a
fresh delegated credential from the agent's sidecar. The boundary therefore sees the person and the agent, never the
agent alone, and no credential is reused.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "semantics/core/fintech-core.ttl"
REQUIRED_CORE_VERSION = "1.0.0"
PRODUCT_SCORES = "risk-compliance.risk-scores"
PRODUCT_NOTES = "risk-compliance.risk-review-notes"
AGENT_SPIFFE_ID = "spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent"
SCORE_COLUMNS = "customer_iri,risk_band,scored_at"
PURPOSE = "risk-review"


class CoreVersionMismatch(RuntimeError):
    pass


def core_version(path: Path = CORE) -> str:
    match = re.search(r'owl:versionInfo\s+"([^"]+)"', Path(path).read_text())
    if match is None:
        raise CoreVersionMismatch("the shared core declares no version")
    return match.group(1)


def review_note_turtle(note_id: str, customer_iri: str, band: str, scored_on: str, now: datetime) -> str:
    text = f"High band, last scored {scored_on}. Re-score before the next decision."
    return f'''@prefix fintech: <https://chakracommerce.com/ontology/fintech/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
<https://chakracommerce.com/ontology/fintech/review/{note_id}> a fintech:ReviewNote ;
  fintech:noteId "{note_id}" ;
  fintech:forCustomer <{customer_iri}> ;
  fintech:riskBand "{band}" ;
  fintech:reviewedNote "{text}" ;
  fintech:sourceSystem "{AGENT_SPIFFE_ID}" ;
  fintech:sourceIngestionTime "{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"^^xsd:dateTime .
'''


@dataclass
class AgentRun:
    snapshot_sha256: str = ""
    high_risk_stale: List[str] = field(default_factory=list)
    proposals: List[dict] = field(default_factory=list)
    refusals: List[tuple] = field(default_factory=list)


class RiskReviewAgent:
    def __init__(self, channel, *, now: Callable[[], datetime],
                 threshold: timedelta = timedelta(days=90), limit: Optional[int] = None):
        self.channel = channel
        self.now = now
        self.threshold = threshold
        self.limit = limit

    def run(self) -> AgentRun:
        version = core_version()
        if version != REQUIRED_CORE_VERSION:
            raise CoreVersionMismatch(f"agent is built for core {REQUIRED_CORE_VERSION}, found {version}")

        result = AgentRun()
        read = self.channel.get(f"/products/{PRODUCT_SCORES}/rows?columns={SCORE_COLUMNS}&purpose={PURPOSE}")
        if read.status_code != 200:
            raise RuntimeError(f"reading the scores was refused: {read.status_code} {read.text}")
        body = read.json()
        result.snapshot_sha256 = body["snapshot_sha256"]

        cutoff = self.now() - self.threshold
        stale = [row for row in body["rows"]
                 if row["risk_band"] == "high" and datetime.fromisoformat(row["scored_at"].replace("Z", "+00:00")) < cutoff]
        if self.limit is not None:
            stale = stale[: self.limit]
        result.high_risk_stale = [row["customer_iri"] for row in stale]

        for row in stale:
            scored_on = row["scored_at"][:10]
            note_id = f"RN-{scored_on.replace('-', '')}-{row['customer_iri'].rsplit('#', 1)[1][:8]}"
            payload = review_note_turtle(note_id, row["customer_iri"], row["risk_band"], scored_on, self.now())
            response = self.channel.post(
                f"/products/{PRODUCT_NOTES}/proposals",
                json={"format": "turtle", "payload": payload, "derived_from": [result.snapshot_sha256]},
            )
            if response.status_code == 201:
                result.proposals.append(response.json())
            else:
                result.refusals.append((note_id, response.status_code, response.json().get("detail")))
        return result
