"""Direct writes (addendum W2): what a service or an agent may write now, and what waits for an owner.

The gates run in this order, and each one fails closed:
  1. the product has a write contract, and the rows match it (columns, key, size)
  2. the effective classification of what is written (an unclassified column is personal)
  3. identity: a customer writes only their own record (the minted customer IRI, from the verified kyc_id)
  4. the outcome, from the platform's write table and the domain's (stricter only): direct, a proposal, or refused
  5. the write grant, separate from read and propose (authorize), and person ∩ agent ∩ product policy
  6. read-before-write: an agent's derived write cites the snapshots it read, through this boundary
  7. rate limits, and the shapes (SHACL) for the product
  8. publish: the audit record is written first; then the new snapshot, signed with lineage
"""

from typing import Dict, List, Optional

from proposals.payload import PayloadError
from proposals.writer import GovernedWriter
from shared.governance.products import product_policy_input
from shared.semantic.identity import IriKeyMissingError, mint_customer_iri
from shared.semantic.validation import validate_graph, violation_messages

from . import writes as w
from .pipeline import Denied, Services, _base_input, authorize
from .policy import decide_write_outcome
from .proposals import Limits, _rate

MAX_ROWS = w.MAX_ROWS
SHAPES = {
    "accounts.customer-intake": "write-customer-intake",
    "risk-compliance.score-freshness-summary": "write-score-freshness-summary",
    "risk-compliance.risk-scores": "write-risk-scores",
}


def _kyc_id(caller) -> Optional[str]:
    """The verified kyc_id of the person the call acts for, or of the caller's own session."""
    value = caller.delegation.attributes.get("kyc_id") if caller.delegation is not None \
        else caller.principal.claims.get("kyc_id")
    return value if isinstance(value, str) and value else None


def _record_is_theirs(caller, rows: List[dict]) -> bool:
    """A customer's record is theirs when its customer_iri is the one minted from their identity. Fails closed."""
    kyc = _kyc_id(caller)
    if not kyc:
        return False
    try:
        expected = mint_customer_iri(caller.principal.subject, kyc)
    except IriKeyMissingError:
        return False
    return all(row.get("customer_iri") == expected for row in rows)


async def direct_write(services: Services, writer: Optional[GovernedWriter], limits: Limits, caller,
                       product_id: str, rows: List[dict], derived_from: List[str]) -> Dict:
    product = services.products.get(product_id)
    if product is None:
        raise Denied(404, "product not found")
    if writer is None or writer.product_id != product_id:
        raise Denied(404, "this product takes no direct writes")

    try:
        contract = w.contract(product)
    except w.WriteContractError as exc:
        raise PayloadError(422, str(exc)) from exc
    if not isinstance(rows, list) or not rows:
        raise PayloadError(400, "rows must be a non-empty list")
    if len(rows) > MAX_ROWS:
        raise PayloadError(413, f"at most {MAX_ROWS} rows per write")
    columns = sorted({column for row in rows if isinstance(row, dict) for column in row})
    unknown = [column for column in columns if column not in writer.columns]
    if unknown:
        raise PayloadError(400, f"unknown columns: {', '.join(unknown)}")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(contract["key"]), str) or not row.get(contract["key"]):
            raise PayloadError(400, f"every row needs a non-empty {contract['key']}")
    rows = [w.complete(row, writer.columns) for row in rows]

    effective = w.effective_classification(product, columns)
    caller_kind = "agent" if caller.delegation is not None else "service"
    principal = caller.principal.subject
    producer = caller.spiffe_id in contract["producers"]

    # 3. identity: a record that names a customer is written only for that customer.
    subject_match = False
    intake_grant = False
    if contract["kind"] == "captured":
        if _kyc_id(caller) is not None:
            subject_match = _record_is_theirs(caller, rows)
        if caller.delegation is not None:
            intake_grant = services.grants.find_valid(
                subject=principal, workload_spiffe_id=caller.spiffe_id, product_id=product_id,
                columns=columns, purpose="intake", now=services.clock(),
            ) is not None
        if _kyc_id(caller) is not None and not (subject_match or intake_grant):
            raise Denied(403, "a customer may write only their own record")

    # 4. the outcome (platform, then the domain may only be stricter)
    base = _base_input(caller, product_policy_input(product), "write", columns)
    base["write"] = {
        "kind": contract["kind"],
        "classification": effective,
        "caller": caller_kind,
        "producer": producer,
        "subject_or_grant": bool(subject_match or intake_grant),
    }
    try:
        outcome = await decide_write_outcome(base)
    except Exception as exc:  # OPA unreachable or malformed: refuse, never guess
        raise Denied(503, "policy unavailable; nothing written") from exc
    if outcome == "refused_pii":
        raise PayloadError(422, "agent_cannot_create_pii")
    if outcome == "requires_owner_review":
        raise Denied(409, f"requires_owner_review: propose at /products/{product_id}/proposals")
    if outcome == "forbidden":
        raise Denied(403, "this caller may not write this data directly")

    # 5. the write grant, and person ∩ agent ∩ product policy
    _, grant = await authorize(services, caller, product_id, "write", columns, purpose="write")

    # 6. read-before-write, for an agent's derived write
    cited: List[str] = []
    if caller.delegation is not None and contract["kind"] == "derived":
        cited = list(dict.fromkeys(derived_from or []))
        if not cited:
            raise PayloadError(422, "a derived write by an agent must cite the snapshots it was derived from")
        missing = services.ledger.unread(subject=principal, actor=caller.spiffe_id, digests=cited,
                                         since=caller.delegation.issued_at)
        if missing:
            raise Denied(403, "derived_from cites a snapshot this agent did not read through the boundary "
                              "for this person within the delegation")

    # 7. rate limits and the shapes
    now = services.clock()
    _rate(limits.agent, caller.spiffe_id, now)
    _rate(limits.person, principal, now)
    conforms, report_graph, report = validate_graph(w.rows_to_graph(product_id, rows), SHAPES[product_id])
    if not conforms:
        raise PayloadError(422, "rows do not conform to the shapes: "
                           + "; ".join(violation_messages(report_graph) or [report]))

    # 8. publish: merge into the product's current state, then the audit record, then the snapshot
    try:
        merged = w.merge(writer.current_rows(), rows, contract["key"], contract["mode"])
    except w.WriteConflict as exc:
        raise Denied(409, str(exc)) from exc
    revisions = services.revisions
    policy_rev = f"{revisions['platform']}/{revisions['domains'].get(product_id, 'missing')}"
    delegated = caller.delegation is not None
    prepared = writer.prepare_write(
        rows=merged, written_by=caller.spiffe_id,
        on_behalf_of=principal if delegated else None,
        actor_chain=list(caller.delegation.chain) if delegated else [],
        derived_from=cited, write_kind=contract["kind"], outcome="direct",
        policy_revision=policy_rev, now=now,
    )
    await services.audit({**prepared.audit_record, "subject": principal,
                          "workload_spiffe_id": caller.spiffe_id, "grant_id": grant.id if grant else None,
                          "columns": columns, "classification": effective, "write_outcome": outcome})
    prepared.commit()
    return {"product_id": product_id, "outcome": outcome, "rows_written": len(rows),
            "snapshot_sha256": writer.current_digest(), "accepted_by": f"policy:{policy_rev}",
            "grant_id": grant.id if grant else None}

