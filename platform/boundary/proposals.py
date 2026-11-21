"""The proposal endpoints' flows. Each one runs the platform's checks, then the writer's two-phase publish.

Every refusal is fail closed and nothing is written: a proposal must be authorized, parse, conform to the shapes,
cite snapshots its agent read, and fit the rate limits. Owner actions must come from the owner, never a delegate.
"""

from datetime import timedelta
from typing import List

from proposals.limits import RateLimited, RateLimiter
from proposals.payload import PayloadError, parse_payload, review_note_rows, validate_payload
from proposals.writer import GovernedWriter

from .pipeline import Denied, Services, authorize


class Limits:
    def __init__(self, per_agent: int = 20, per_person: int = 50, window: timedelta = timedelta(hours=1)):
        self.agent = RateLimiter(per_agent, window)
        self.person = RateLimiter(per_person, window)


def _rate(limiter: RateLimiter, key: str, now) -> None:
    try:
        limiter.take(key, now)
    except RateLimited as exc:
        raise Denied(429, "rate limit reached") from exc


async def propose(services: Services, writer: GovernedWriter, limits: Limits, caller, product_id: str,
                  payload: bytes, fmt: str, derived_from: List[str]) -> dict:
    if caller.delegation is None:
        raise Denied(403, "only a delegated caller may propose")
    if product_id != writer.product_id:
        raise Denied(404, "this product takes no proposals")
    await authorize(services, caller, product_id, "propose", [], purpose="propose")

    now = services.clock()
    _rate(limits.agent, caller.spiffe_id, now)
    _rate(limits.person, caller.principal.subject, now)

    graph = parse_payload(payload, fmt)
    validate_payload(graph)
    rows = review_note_rows(graph)

    cited = list(dict.fromkeys(derived_from))
    if not cited:
        raise PayloadError(422, "derived_from must cite the snapshot digests the proposal was derived from")
    missing = services.ledger.unread(
        subject=caller.principal.subject, actor=caller.spiffe_id, digests=cited,
        since=caller.delegation.issued_at,
    )
    if missing:
        raise Denied(403, "derived_from cites a snapshot this agent did not read through the boundary "
                          "for this person within the delegation")

    proposal_id = writer.new_id()
    prepared = writer.prepare_proposal(
        proposal_id=proposal_id, on_behalf_of=caller.principal.subject, actor_chain=list(caller.delegation.chain),
        derived_from=cited, payload=payload, rows=rows, now=now,
    )
    await services.audit({**prepared.audit_record, "subject": caller.principal.subject,
                          "workload_spiffe_id": caller.spiffe_id})
    prepared.commit()
    return writer.view(writer.get(proposal_id))


async def decide(services: Services, writer: GovernedWriter, caller, product_id: str, proposal_id: str,
                 action: str, reason: str = "") -> dict:
    await authorize(services, caller, product_id, action, [], purpose="")
    now = services.clock()
    writer.expire_due(now)
    if action == "accept":
        prepared = writer.prepare_accept(proposal_id, accepted_by=caller.principal.subject, now=now)
    elif action == "reject":
        prepared = writer.prepare_reject(proposal_id, rejected_by=caller.principal.subject, reason=reason, now=now)
    else:
        raise ValueError(f"unknown decision {action}")
    await services.audit({**prepared.audit_record, "subject": caller.principal.subject,
                          "workload_spiffe_id": caller.spiffe_id})
    prepared.commit()
    return writer.view(writer.get(proposal_id))


async def rollback(services: Services, writer: GovernedWriter, caller, product_id: str, reason: str) -> dict:
    await authorize(services, caller, product_id, "rollback", [], purpose="")
    now = services.clock()
    prepared = writer.prepare_rollback(decided_by=caller.principal.subject, reason=reason, now=now)
    await services.audit({**prepared.audit_record, "subject": caller.principal.subject,
                          "workload_spiffe_id": caller.spiffe_id})
    prepared.commit()
    return {"product_id": product_id, "current_digest": writer.current_digest(), "versions": writer.versions()}
