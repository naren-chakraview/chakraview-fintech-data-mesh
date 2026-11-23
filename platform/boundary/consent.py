"""Subject-consent proposals (addendum 2, W7).

An agent derived a personal value that describes exactly one customer (her canonical address, say). The agent does not
write it: it proposes it to her. The proposal carries the value being replaced and the value proposed, so she sees both.
Only she can accept or decline it, with her own identity, never through the agent that proposed it, and never through the
domain owner. The proposal passes the same automated gates as any proposal: delegation, a propose grant, policy, the
contract, the shapes, rate limits, and read-before-write citations.
"""

import hashlib
import json
from typing import List, Optional

from proposals.payload import PayloadError
from proposals.writer import GovernedWriter, ProposalConflict, ProposalNotFound
from shared.semantic.identity import IriKeyMissingError, mint_customer_iri
from shared.semantic.validation import validate_graph, violation_messages

from . import writes as w
from .direct_writes import SHAPES
from .pipeline import Denied, Services, authorize
from .proposals import Limits, _rate


def _subject_of(caller) -> Optional[str]:
    """The customer identifier the caller's own IdP-attested identity mints (None when it cannot be minted)."""
    kyc = caller.principal.claims.get("kyc_id")
    if not isinstance(kyc, str) or not kyc:
        return None
    try:
        return mint_customer_iri(caller.principal.subject, kyc)
    except IriKeyMissingError:
        return None


def _delegator_subject(caller) -> Optional[str]:
    """The customer identifier of the person this agent acts for, minted from the kyc_id the gateway carried in the
    delegated token (user_attributes, v0.4.4). None when it is absent."""
    kyc = caller.delegation.attributes.get("kyc_id") if caller.delegation is not None else None
    if not isinstance(kyc, str) or not kyc:
        return None
    try:
        return mint_customer_iri(caller.principal.subject, kyc)
    except IriKeyMissingError:
        return None


def _view(record: dict) -> dict:
    return {
        "id": record["id"],
        "product_id": record["product_id"],
        "status": record["status"],
        "subject": record.get("subject"),
        "on_behalf_of": record["on_behalf_of"],
        "actor_chain": record["actor_chain"],
        "derived_from": record["derived_from"],
        "replaces": record.get("replaces"),
        "proposed": record.get("proposed"),
        "expires_at": record["expires_at"].isoformat(),
        "decided_by": record["decided_by"],
        "reason": record["reason"],
    }


async def propose_consent(services: Services, writer: GovernedWriter, limits: Limits, caller, product_id: str,
                          rows: List[dict], derived_from: List[str]) -> dict:
    product = services.products.get(product_id)
    if product is None:
        raise Denied(404, "product not found")
    if writer is None or writer.product_id != product_id:
        raise Denied(404, "this product takes no consent proposals")
    try:
        contract = w.contract(product)
    except w.WriteContractError as exc:
        raise PayloadError(422, str(exc)) from exc
    if not contract["subject_consent"]:
        raise PayloadError(422, "this product takes no subject-consent proposals")
    if caller.delegation is None:
        raise Denied(403, "only an agent acting for the data subject proposes consent")
    if not isinstance(rows, list) or len(rows) != 1:
        raise PayloadError(422, "a consent proposal describes exactly one data subject: one row")

    row = w.complete(rows[0], writer.columns)
    subject = row.get("customer_iri")
    if not isinstance(subject, str) or not subject:
        raise PayloadError(422, "the row must name its data subject (customer_iri)")

    # C1: an agent proposes consent only for the person it acts for. Her identifier, minted from the kyc_id her
    # gateway-signed token carries, must be the record's customer_iri. The one exception is staff holding the intake
    # grant, who onboard a customer on her behalf. Checked before anything is recorded: no proposal exists otherwise.
    if _delegator_subject(caller) != subject:
        staff = services.grants.find_valid(
            subject=caller.principal.subject, workload_spiffe_id=caller.spiffe_id, product_id=product_id,
            columns=writer.columns, purpose="intake", now=services.clock(),
        )
        if staff is None:
            raise Denied(403, "an agent proposes consent only for the person it acts for")
    current = next((r for r in writer.current_rows() if r.get("customer_iri") == subject), None)
    if current is None:
        raise PayloadError(422, "there is no record of this customer to replace")

    cited = list(dict.fromkeys(derived_from or []))
    if not cited:
        raise PayloadError(422, "a consent proposal must cite the snapshots it was derived from")
    principal = caller.principal.subject
    missing = services.ledger.unread(subject=principal, actor=caller.spiffe_id, digests=cited,
                                     since=caller.delegation.issued_at)
    if missing:
        raise Denied(403, "derived_from cites a snapshot this agent did not read through the boundary "
                          "for this person within the delegation")

    await authorize(services, caller, product_id, "propose", writer.columns, purpose="propose")
    now = services.clock()
    _rate(limits.agent, caller.spiffe_id, now)
    _rate(limits.person, principal, now)

    conforms, report_graph, report = validate_graph(w.rows_to_graph(product_id, [row]), SHAPES[product_id])
    if not conforms:
        raise PayloadError(422, "rows do not conform to the shapes: "
                           + "; ".join(violation_messages(report_graph) or [report]))

    proposal_id = writer.new_id()
    payload = json.dumps({"replaces": current, "proposed": row}, sort_keys=True).encode()
    prepared = writer.prepare_proposal(
        proposal_id=proposal_id, on_behalf_of=principal, actor_chain=list(caller.delegation.chain),
        derived_from=cited, payload=payload, rows=[row], now=now,
    )
    await services.audit({**prepared.audit_record, "action": "propose_consent", "subject": principal,
                          "workload_spiffe_id": caller.spiffe_id, "consent_subject": subject,
                          "payload_sha256": hashlib.sha256(payload).hexdigest()})
    prepared.commit()
    record = writer.get(proposal_id)
    record.update({"kind": "consent", "subject": subject, "replaces": current, "proposed": row})
    return _view(record)


async def decide_consent(services: Services, writer: GovernedWriter, caller, product_id: str, proposal_id: str,
                         action: str, reason: str = "") -> dict:
    """The data subject accepts or declines a consent proposal. Only she can: the platform checks her identity, and
    an agent (any delegation) or the domain owner never matches."""
    if writer is None or writer.product_id != product_id:
        raise Denied(404, "this product takes no consent proposals")
    if caller.delegation is not None:
        raise Denied(403, "only the data subject accepts or declines her own consent")
    try:
        record = writer.get(proposal_id)
    except ProposalNotFound as exc:
        raise Denied(404, "proposal not found") from exc
    if record.get("kind") != "consent":
        raise ProposalConflict("this proposal is not a subject-consent proposal")

    subject_match = _subject_of(caller) == record.get("subject")
    await authorize(services, caller, product_id, "accept_consent", [], purpose="",
                    extra_input={"consent": {"subject_match": subject_match}})

    now = services.clock()
    if action == "accept":
        prepared = writer.prepare_consent_accept(proposal_id, accepted_by=caller.principal.subject, now=now)
    else:
        prepared = writer.prepare_reject(proposal_id, rejected_by=caller.principal.subject,
                                         reason=reason or "declined by the data subject", now=now)
    await services.audit({**prepared.audit_record, "subject": caller.principal.subject,
                          "workload_spiffe_id": caller.spiffe_id, "consent_subject": record.get("subject")})
    prepared.commit()
    return _view(writer.get(proposal_id))

