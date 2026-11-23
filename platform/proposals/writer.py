"""The governed writer: proposals, owner decisions and the signed snapshots they produce.

State lives in this process (production: the shared store). Every change that reaches the authoritative product
is a new snapshot, written with a DSSE statement signed by the boundary's governed-writer key. The statement's
predicate names the agent, the person, the chain, the inputs and the acceptance, so lineage can answer "which
agent, for whom, read what, proposed what, and who accepted it".

Two-phase: prepare_* builds everything and can fail with nothing changed; commit() publishes it. The boundary
writes the audit record between the two, so an action that cannot be audited is never published.
"""

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from cryptography.hazmat.primitives import serialization

from lineage.attest import STATEMENT_TYPE, build_statement, sign_envelope

PROPOSAL_PREDICATE_TYPE = "https://chakracommerce.com/data-provenance/proposal/v1"
SNAPSHOT_COLUMNS = ["note_id", "customer_iri", "risk_band", "reviewed_note"]
OPEN = "pending"


class ProposalNotFound(LookupError):
    pass


class ProposalConflict(Exception):
    """The request is valid but the state does not allow it (already decided, expired, duplicate note)."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_bytes(rows: List[dict], columns: Optional[List[str]] = None) -> bytes:
    return (json.dumps({"columns": list(columns or SNAPSHOT_COLUMNS), "rows": rows}, sort_keys=True, indent=2)
            + "\n").encode()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


@dataclass
class Prepared:
    """A change ready to publish. The audit record goes out before commit(); nothing changes until then."""

    audit_record: dict
    _commit: Callable[[], None]

    def commit(self) -> None:
        self._commit()


class GovernedWriter:
    def __init__(self, *, product_id: str, snapshot_dir: Path, attestation_dir: Path, history_dir: Path,
                 private_key_pem: bytes, keyid: str, producer_spiffe_id: str,
                 clock: Callable[[], datetime], ttl: timedelta = timedelta(days=2), code_commit: str = "unknown",
                 columns: Optional[List[str]] = None, seed_dir: Optional[Path] = None):
        self.product_id = product_id
        self.columns = list(columns or SNAPSHOT_COLUMNS)
        self.snapshot_dir = Path(snapshot_dir)
        self.attestation_dir = Path(attestation_dir)
        self.history_dir = Path(history_dir)
        self._key = serialization.load_pem_private_key(private_key_pem, password=None)
        self.keyid = keyid
        self.producer = producer_spiffe_id
        self.clock = clock
        self.ttl = ttl
        self.code_commit = code_commit
        self.proposals: dict = {}

        target = self.snapshot_dir / f"{product_id}.json"
        if not target.exists():
            # The first version: the seed (for a product that starts from a fixture), or an empty snapshot. It is signed
            # like every later version, so the product's lineage starts with the boundary's own statement.
            seed = Path(seed_dir) / f"{product_id}.json" if seed_dir else None
            data = seed.read_bytes() if seed is not None and seed.exists() else snapshot_bytes([], self.columns)
            self._publish_initial(data, now=clock())
        current = target.read_bytes()
        self._versions: List[dict] = [{
            "digest": _sha256(current),
            "rows": json.loads(current)["rows"],
            "action": "initial",
        }]

    def _publish_initial(self, data: bytes, now: datetime) -> None:
        statement = build_statement(self.product_id, data, self.producer, self.code_commit, [], now)
        statement["predicate"].update({"action": "initial"})
        envelope = sign_envelope(statement, self._key, self.keyid)
        _atomic_write(self.snapshot_dir / f"{self.product_id}.json", data)
        _atomic_write(self.attestation_dir / f"{self.product_id}.dsse.json",
                      (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode())
        _atomic_write(self.history_dir / f"{_sha256(data)}.json", data)

    def current_rows(self) -> List[dict]:
        return [dict(row) for row in self._versions[-1]["rows"]]

    # ---- reads -------------------------------------------------------------------------------------------

    def current_digest(self) -> str:
        return self._versions[-1]["digest"]

    def versions(self) -> List[dict]:
        return [{"version": i, "digest": v["digest"], "action": v["action"]} for i, v in enumerate(self._versions)]

    def get(self, proposal_id: str) -> dict:
        record = self.proposals.get(proposal_id)
        if record is None or record["product_id"] != self.product_id:
            raise ProposalNotFound(proposal_id)
        self._expire_if_due(record)
        return record

    def view(self, record: dict) -> dict:
        return {
            "id": record["id"],
            "product_id": record["product_id"],
            "status": record["status"],
            "on_behalf_of": record["on_behalf_of"],
            "actor_chain": record["actor_chain"],
            "derived_from": record["derived_from"],
            "expires_at": record["expires_at"].isoformat(),
            "decided_by": record["decided_by"],
            "decided_at": record["decided_at"].isoformat() if record["decided_at"] else None,
            "reason": record["reason"],
            "statement_sha256": record["statement_sha256"],
        }

    # ---- proposals ---------------------------------------------------------------------------------------

    def new_id(self) -> str:
        return f"prop_{uuid.uuid4().hex[:16]}"

    def prepare_proposal(self, *, proposal_id: str, on_behalf_of: str, actor_chain: List[str],
                         derived_from: List[str], payload: bytes, rows: List[dict], now: datetime) -> Prepared:
        expires_at = now + self.ttl
        statement = {
            "_type": STATEMENT_TYPE,
            "subject": [{"name": f"proposal:{proposal_id}", "digest": {"sha256": _sha256(payload)}}],
            "predicateType": PROPOSAL_PREDICATE_TYPE,
            "predicate": {
                "product": self.product_id,
                "proposal_id": proposal_id,
                "producer": self.producer,
                "on_behalf_of": on_behalf_of,
                "actor_chain": list(actor_chain),
                "derived_from": [{"sha256": d} for d in derived_from],
                "submitted_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "code_commit": self.code_commit,
            },
        }
        envelope = sign_envelope(statement, self._key, self.keyid)
        envelope_sha = _sha256(json.dumps(envelope, sort_keys=True).encode())
        record = {
            "id": proposal_id,
            "product_id": self.product_id,
            "status": OPEN,
            "on_behalf_of": on_behalf_of,
            "actor_chain": list(actor_chain),
            "derived_from": list(derived_from),
            "rows": rows,
            "payload": payload,
            "created_at": now,
            "expires_at": expires_at,
            "decided_by": None,
            "decided_at": None,
            "reason": None,
            "statement": envelope,
            "statement_sha256": envelope_sha,
        }
        audit = {
            "action": "propose",
            "decision": "allow",
            "product": self.product_id,
            "proposal_id": proposal_id,
            "on_behalf_of": on_behalf_of,
            "actor_chain": list(actor_chain),
            "derived_from": list(derived_from),
            "payload_sha256": _sha256(payload),
            "row_count": len(rows),
            "statement_sha256": envelope_sha,
            "expires_at": expires_at.isoformat(),
            "timestamp": now.isoformat(),
        }

        def commit() -> None:
            self.proposals[proposal_id] = record

        return Prepared(audit, commit)

    # ---- owner decisions ---------------------------------------------------------------------------------

    def prepare_accept(self, proposal_id: str, *, accepted_by: str, now: datetime) -> Prepared:
        record = self._open_record(proposal_id, now)
        current = self._versions[-1]["rows"]
        clashes = sorted({r["note_id"] for r in record["rows"]} & {r["note_id"] for r in current})
        if clashes:
            raise ProposalConflict(f"note_id already exists in the product: {', '.join(clashes)}")
        rows = sorted(current + record["rows"], key=lambda r: r["note_id"])
        extra = {
            "proposal_id": proposal_id,
            "proposal_statement_sha256": record["statement_sha256"],
            "on_behalf_of": record["on_behalf_of"],
            "actor_chain": record["actor_chain"],
            "derived_from": [{"sha256": d} for d in record["derived_from"]],
            "accepted_by": accepted_by,
        }

        def after_publish() -> None:
            record["status"] = "accepted"
            record["decided_by"] = accepted_by
            record["decided_at"] = now
        return self._prepare_publish(rows, "accept", now, accepted_by, extra, after_publish)

    def prepare_consent_accept(self, proposal_id: str, *, accepted_by: str, now: datetime) -> Prepared:
        """The data subject accepts a consent proposal: her proposed row replaces the row it was proposed against. The
        snapshot's statement names the subject as acceptor, the agent in the chain, and the snapshot the agent read."""
        record = self._open_record(proposal_id, now)
        if record.get("kind") != "consent":
            raise ProposalConflict("not a subject-consent proposal")
        current = self._versions[-1]["rows"]
        subject = record["subject"]
        existing = next((r for r in current if r.get("customer_iri") == subject), None)
        if existing != record["replaces"]:
            raise ProposalConflict("the value changed since it was proposed")
        proposed = dict(record["proposed"])
        rows = sorted([r for r in current if r.get("customer_iri") != subject] + [proposed],
                      key=lambda r: str(r["customer_iri"]))
        extra = {
            "proposal_id": proposal_id,
            "proposal_statement_sha256": record["statement_sha256"],
            "on_behalf_of": record["on_behalf_of"],
            "actor_chain": record["actor_chain"],
            "derived_from": [{"sha256": d} for d in record["derived_from"]],
            "accepted_by": accepted_by,
            "write_kind": "captured",
            "consent": "subject",
        }

        def after_publish() -> None:
            record["status"] = "accepted"
            record["decided_by"] = accepted_by
            record["decided_at"] = now
        return self._prepare_publish(rows, "accept_consent", now, accepted_by, extra, after_publish)

    def prepare_reject(self, proposal_id: str, *, rejected_by: str, reason: str, now: datetime) -> Prepared:
        record = self._open_record(proposal_id, now)
        if not reason:
            raise ProposalConflict("a rejection needs a reason")
        audit = {
            "action": "reject", "decision": "allow", "product": self.product_id, "proposal_id": proposal_id,
            "rejected_by": rejected_by, "reason": reason, "on_behalf_of": record["on_behalf_of"],
            "actor_chain": record["actor_chain"], "derived_from": record["derived_from"],
            "statement_sha256": record["statement_sha256"], "timestamp": now.isoformat(),
        }

        def commit() -> None:
            record["status"] = "rejected"
            record["decided_by"] = rejected_by
            record["decided_at"] = now
            record["reason"] = reason
        return Prepared(audit, commit)

    def prepare_rollback(self, *, decided_by: str, reason: str, now: datetime) -> Prepared:
        if len(self._versions) < 2:
            raise ProposalConflict("there is no earlier snapshot to roll back to")
        if not reason:
            raise ProposalConflict("a rollback needs a reason")
        previous = self._versions[-2]
        extra = {"rolled_back_from": self.current_digest(), "rolled_back_to": previous["digest"], "reason": reason}
        return self._prepare_publish(list(previous["rows"]), "rollback", now, decided_by, extra, lambda: None)

    def expire_due(self, now: datetime) -> List[str]:
        expired = []
        for record in self.proposals.values():
            if record["product_id"] == self.product_id and self._expire_if_due(record, now):
                expired.append(record["id"])
        return expired

    # ---- internals ---------------------------------------------------------------------------------------

    def _expire_if_due(self, record: dict, now: Optional[datetime] = None) -> bool:
        now = now or self.clock()
        if record["status"] == OPEN and now >= record["expires_at"]:
            record["status"] = "expired"
            return True
        return False

    def _open_record(self, proposal_id: str, now: datetime) -> dict:
        record = self.get(proposal_id)
        if record["status"] != OPEN:
            raise ProposalConflict(f"proposal is already {record['status']}")
        if now >= record["expires_at"]:
            raise ProposalConflict("proposal has expired")
        return record

    def prepare_write(self, *, rows: List[dict], written_by: str, on_behalf_of: Optional[str],
                      actor_chain: List[str], derived_from: List[str], write_kind: str, outcome: str,
                      policy_revision: str, now: datetime) -> Prepared:
        """A direct write: the new snapshot is published when the write is decided, not after an owner's review. The
        statement names the writer, the person and agent when there are any, the inputs it was derived from, the kind
        of write, and the policy revision that allowed it. `rows` is the complete new state of the product."""
        extra = {
            "written_by": written_by,
            "on_behalf_of": on_behalf_of,
            "actor_chain": list(actor_chain),
            "write_kind": write_kind,
            "outcome": outcome,
            "accepted_by": f"policy:{policy_revision}",
            "derived_from": [{"sha256": d} for d in derived_from],
        }
        return self._prepare_publish(rows, "write", now, f"policy:{policy_revision}", extra, lambda: None)

    def _prepare_publish(self, rows: List[dict], action: str, now: datetime, decided_by: str, extra: dict,
                         after: Callable[[], None]) -> Prepared:
        data = snapshot_bytes(rows, self.columns)
        digest = _sha256(data)
        inputs = list(extra.get("derived_from", []))
        statement = build_statement(self.product_id, data, self.producer, self.code_commit, inputs, now)
        statement["predicate"].update({"action": action, "decided_by": decided_by, **extra})
        envelope = sign_envelope(statement, self._key, self.keyid)
        envelope_bytes = (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode()
        audit = {"action": action, "decision": "allow", "product": self.product_id, "snapshot_sha256": digest,
                 "decided_by": decided_by, "timestamp": now.isoformat(), **extra}
        if "derived_from" in extra:  # the audit keeps plain digests; the signed predicate uses the in-toto form
            audit["derived_from"] = [d["sha256"] for d in extra["derived_from"]]

        def commit() -> None:
            _atomic_write(self.snapshot_dir / f"{self.product_id}.json", data)
            _atomic_write(self.attestation_dir / f"{self.product_id}.dsse.json", envelope_bytes)
            _atomic_write(self.history_dir / f"{digest}.json", data)
            self._versions.append({"digest": digest, "rows": rows, "action": action})
            after()
        return Prepared(audit, commit)
