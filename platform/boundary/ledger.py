"""The boundary's own record of allowed reads, fed from the same audit records it writes.

A proposal may cite a snapshot only if this person and this agent actually read that snapshot through the
boundary, within the delegation's lifetime. The check reads this ledger, not the agent's word.
"""

from datetime import datetime
from typing import Iterable, List, Set


class ReadLedger:
    def __init__(self) -> None:
        self._reads: List[dict] = []

    def observe(self, record: dict) -> None:
        """Keep allowed reads. Anything else (denials, owner decisions, proposals) is not a read of data."""
        if record.get("action") != "read" or record.get("decision") != "allow":
            return
        digest = record.get("snapshot_sha256")
        if not digest:
            return
        self._reads.append({
            "subject": record.get("subject"),
            "actor": record.get("workload_spiffe_id"),
            "product": record.get("product"),
            "snapshot_sha256": digest,
            "timestamp": datetime.fromisoformat(record["timestamp"]),
        })

    def unread(self, *, subject: str, actor: str, digests: Iterable[str], since: datetime) -> Set[str]:
        """The cited digests this pair did not read within the window. Empty means every citation holds."""
        seen = {
            r["snapshot_sha256"] for r in self._reads
            if r["subject"] == subject and r["actor"] == actor and r["timestamp"] >= since
        }
        return {d for d in digests if d not in seen}
