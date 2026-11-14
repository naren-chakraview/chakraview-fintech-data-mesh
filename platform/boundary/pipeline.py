"""The read path. Every step fails closed: no verified caller, no decision, no grant, no audit means no data."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional

from governance.enforce import mask_rows
from governance.enforce import opa_decide_strategy
from shared.compliance.masking import ColumnMaskingPolicy
from shared.governance.grants import Grant, GrantStore
from shared.governance.products import CLASSIFICATION_ORDER, column_classifications, product_policy_input
from shared.identity import Caller

from .policy import Decision
from .reader import FixtureReader
from .sparql import (PII_PREDICATE_NAMES, QueryParseError, ReadOnlyViolation, forward_read,
                     parse_read_only, projected_predicates)


class Denied(Exception):
    """The read is refused. status is the HTTP status to return; no data is included."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class Services:
    products: Dict[str, dict]
    reader: FixtureReader
    grants: GrantStore
    decide: Callable[[dict], Awaitable[Decision]]
    audit: Callable[[dict], Awaitable[None]]
    lineage_check: Callable[[str, bytes], bool]
    revisions: dict
    clock: Callable[[], datetime]
    sparql_endpoints: Dict[str, str] = field(default_factory=dict)
    sparql_transport: object = None


def _base_input(caller: Caller, product: dict, action: str) -> dict:
    return {
        "action": action,
        "principal": {
            "subject": caller.principal.subject,
            "roles": sorted(caller.principal.roles),
        },
        "workload": {"spiffe_id": caller.spiffe_id},
        "product": product,
    }


async def _deny(services: Services, caller: Caller, product_id: str, columns: List[str],
                purpose: str, reason: str, status: int) -> Denied:
    """Audit the refusal. If the audit write fails, the refusal still stands."""
    try:
        await services.audit({
            "timestamp": services.clock().isoformat(),
            "decision": "deny",
            "reason": reason,
            "subject": caller.principal.subject,
            "roles": sorted(caller.principal.roles),
            "workload_spiffe_id": caller.spiffe_id,
            "product": product_id,
            "columns": columns,
            "purpose": purpose,
            "policy_revisions": services.revisions,
        })
    except Exception:
        pass
    return Denied(status, reason)


async def authorize(services: Services, caller: Caller, product_id: str, action: str,
                    columns: List[str], purpose: str) -> tuple:
    """Return (product, grant or None). Raises Denied for a refusal and OPAError/other errors for a broken dependency."""
    product = services.products.get(product_id)
    if product is None:
        raise Denied(404, "product not found")

    policy_input = _base_input(caller, product_policy_input(product), action)
    decision = await services.decide(policy_input)
    if not decision.allow:
        raise await _deny(services, caller, product_id, columns, purpose,
                          "policy denies this read", 403)

    grant: Optional[Grant] = None
    if decision.requires_approval:
        grant = services.grants.find_valid(
            subject=caller.principal.subject,
            workload_spiffe_id=caller.spiffe_id,
            product_id=product_id,
            columns=columns,
            purpose=purpose,
            now=services.clock(),
        )
        if grant is None:
            raise await _deny(services, caller, product_id, columns, purpose,
                              "approval required: no valid grant", 403)
    return product, grant


def _policy_for(product: dict, product_id: str) -> ColumnMaskingPolicy:
    policy = ColumnMaskingPolicy()
    for column, classification in column_classifications(product).items():
        policy.add_policy(product_id, column, classification)
    return policy


def _strategy_decider(base_input: dict):
    async def decide_strategy(column: str, classification: Optional[str]) -> str:
        return await opa_decide_strategy({
            **base_input,
            "column": column,
            "column_classification": classification,
        })
    return decide_strategy


async def read_rows(services: Services, caller: Caller, product_id: str,
                    columns: List[str], purpose: str) -> dict:
    if not columns:
        raise Denied(400, "columns is required")
    try:
        known = set(services.reader.columns(product_id))
    except LookupError as exc:
        raise Denied(404, "no data for product") from exc
    unknown = [c for c in columns if c not in known]
    if unknown:
        raise Denied(400, f"unknown columns: {', '.join(unknown)}")

    product, grant = await authorize(services, caller, product_id, "read", columns, purpose)
    rows = services.reader.read(product_id, columns)

    snapshot = services.reader.snapshot(product_id)
    lineage_verified = services.lineage_check(product_id, snapshot)

    base = _base_input(caller, product_policy_input(product), "read")
    masked = await mask_rows(
        rows,
        product_id,
        columns,
        user_id=caller.principal.subject,
        user_role=",".join(sorted(caller.principal.roles)) or "none",
        policy=_policy_for(product, product_id),
        decide_strategy=_strategy_decider(base),
        write_audit=services.audit,
        extra_audit={
            "decision": "allow",
            "subject": caller.principal.subject,
            "roles": sorted(caller.principal.roles),
            "workload_spiffe_id": caller.spiffe_id,
            "product": product_id,
            "purpose": purpose,
            "grant_id": grant.id if grant else None,
            "lineage_verified": lineage_verified,
            "policy_revisions": services.revisions,
            "timestamp": services.clock().isoformat(),
        },
    )
    return {"product_id": product_id, "columns": columns, "rows": masked,
            "lineage_verified": lineage_verified, "grant_id": grant.id if grant else None}


def predicate_classes(product: dict) -> Dict[str, str]:
    """Predicate local name -> classification, for the predicates this product's SPARQL may read.

    A product column maps to its camelCase predicate (fraud_score -> fraudScore). The PII predicates
    are always pii, whichever product they appear in.
    """
    classes = {_camel(column): cls for column, cls in column_classifications(product).items()}
    classes.update({name: "pii" for name in PII_PREDICATE_NAMES})
    return classes


def _camel(column: str) -> str:
    head, *rest = column.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _strictest(classes: List[str]) -> str:
    return max(classes, key=CLASSIFICATION_ORDER.index)


async def read_sparql(services: Services, caller: Caller, product_id: str,
                      query: str, purpose: str) -> dict:
    product = services.products.get(product_id)
    if product is None:
        raise Denied(404, "product not found")
    endpoint = services.sparql_endpoints.get(product["domain"])
    if endpoint is None:
        raise Denied(404, "no SPARQL endpoint for this domain")

    try:
        algebra = parse_read_only(query)
        origins = projected_predicates(algebra)
    except (ReadOnlyViolation, QueryParseError) as exc:
        raise Denied(400, str(exc)) from exc

    known = predicate_classes(product)
    needed = sorted({p for predicates in origins.values() for p in predicates})
    unknown = [p for p in needed if p not in known]
    if unknown:
        raise Denied(400, f"predicates outside this product's contract: {', '.join(unknown)}")

    # Grants are checked against the predicates the query reads, so a grant for one predicate
    # does not open another, and an alias cannot change what is read.
    product, grant = await authorize(services, caller, product_id, "read", needed, purpose)

    results = await forward_read(endpoint, query, transport=services.sparql_transport)
    variables = [v for v in origins if v in results.get("head", {}).get("vars", [])]
    policy = ColumnMaskingPolicy()
    for variable in variables:
        policy.add_policy(product_id, variable,
                          _strictest([known[p] for p in origins[variable]]))

    raw = results.get("results", {}).get("bindings", [])
    rows = [{v: binding[v]["value"] for v in variables if v in binding} for binding in raw]

    base = _base_input(caller, product_policy_input(product), "read")
    masked_rows = await mask_rows(
        rows,
        product_id,
        variables,
        user_id=caller.principal.subject,
        user_role=",".join(sorted(caller.principal.roles)) or "none",
        policy=policy,
        decide_strategy=_strategy_decider(base),
        write_audit=services.audit,
        extra_audit={
            "decision": "allow",
            "channel": "sparql",
            "subject": caller.principal.subject,
            "roles": sorted(caller.principal.roles),
            "workload_spiffe_id": caller.spiffe_id,
            "product": product_id,
            "purpose": purpose,
            "predicates": needed,
            "grant_id": grant.id if grant else None,
            "lineage_verified": False,
            "policy_revisions": services.revisions,
            "timestamp": services.clock().isoformat(),
        },
    )

    bindings = []
    for source, masked in zip(raw, masked_rows):
        bindings.append({
            v: {"type": source[v]["type"], "value": masked.get(v)}
            for v in variables if v in source
        })
    return {"head": {"vars": variables}, "results": {"bindings": bindings},
            "grant_id": grant.id if grant else None}
