"""Answer, from the audit records alone: which agent, for whom, read what, proposed what, and who accepted it.

Works on the records the boundary writes (the same ones the ledger learns from), so an answer can be checked
against the audit store, not against the agent's own report.
"""

from typing import Iterable, List, Optional


def trace_proposal(records: Iterable[dict], proposal_id: str) -> Optional[dict]:
    records = list(records)
    proposed = next((r for r in records if r.get("action") == "propose" and r.get("proposal_id") == proposal_id), None)
    if proposed is None:
        return None
    person = proposed["on_behalf_of"]
    agent = proposed["workload_spiffe_id"]
    cited = set(proposed.get("derived_from", []))
    reads: List[dict] = [
        {"snapshot_sha256": r["snapshot_sha256"], "product": r["product"], "timestamp": r["timestamp"]}
        for r in records
        if r.get("action") == "read" and r.get("decision") == "allow"
        and r.get("subject") == person and r.get("workload_spiffe_id") == agent
        and r.get("snapshot_sha256") in cited
    ]
    decisions = [
        {"action": r["action"], "by": r.get("accepted_by") or r.get("rejected_by") or r.get("decided_by"),
         "timestamp": r["timestamp"]}
        for r in records
        if r.get("proposal_id") == proposal_id and r.get("action") in {"accept", "reject"}
    ]
    return {
        "proposal_id": proposal_id,
        "agent": agent,
        "for_person": person,
        "actor_chain": proposed.get("actor_chain", []),
        "read": reads,
        "proposed_rows": proposed.get("row_count"),
        "proposed_at": proposed["timestamp"],
        "decisions": decisions,
        "accepted_by": next((d["by"] for d in decisions if d["action"] == "accept"), None),
    }
