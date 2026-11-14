"""SPARQL side door: refused forms never reach Fuseki, aliases cannot leak PII, and grants follow predicates."""

from datetime import timedelta

import httpx
import pytest

from shared.testing.harness import WORKLOADS, open_stack

RISK = "risk-compliance.risk-scores"
ENDPOINT = "http://fuseki.test/risk_compliance/sparql"
PREFIX = "PREFIX f: <http://jena.apache.org/fintech#>\n"
SUBJECT = "risk.analyst@chakra.fintech"
PURPOSE = "fraud-review"

RESULTS = {
    "head": {"vars": ["email", "score"]},
    "results": {"bindings": [
        {"email": {"type": "literal", "value": "john@acme.com"}, "score": {"type": "literal", "value": "0.91"}},
    ]},
}
READ = PREFIX + "SELECT ?email ?score WHERE { ?c f:customerEmail ?email . ?c f:fraudScore ?score }"


@pytest.fixture
def sparql_stack():
    seen = []

    def handler(request):
        seen.append(request.content.decode())
        return httpx.Response(200, json=RESULTS)

    transport = httpx.MockTransport(handler)
    ctx = open_stack(fuseki_endpoints={"risk-compliance": ENDPOINT}, sparql_transport=transport)
    try:
        stack = ctx.__enter__()
    except Exception as exc:  # opa missing
        pytest.skip(f"trust stack unavailable: {exc}")
    try:
        yield stack, seen
    finally:
        ctx.__exit__(None, None, None)


def grant(stack, columns):
    stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"], product_id=RISK,
                        columns=columns, purpose=PURPOSE, expires_at=stack.now + timedelta(hours=1))


def post(stack, query, extra=None):
    token = stack.token(SUBJECT, roles=["risk_analyst"])
    body = {"query": query, **(extra or {})}
    return stack.boundary().post(f"/products/{RISK}/sparql?purpose={PURPOSE}", json=body,
                                 headers=stack.headers(token))


@pytest.mark.parametrize("query", [
    PREFIX + 'INSERT DATA { <urn:x> f:customerEmail "a@b.c" }',
    PREFIX + "DELETE WHERE { ?s ?p ?o }",
    "LOAD <http://evil.example/x.ttl>",
    "CLEAR ALL",
    "DROP GRAPH <urn:g>",
    "CREATE GRAPH <urn:g>",
])
def test_update_forms_are_refused_before_fuseki(sparql_stack, query):
    stack, seen = sparql_stack
    grant(stack, ["customerEmail"])

    assert post(stack, query).status_code == 400
    assert seen == []


# R1 regression: a grant for one predicate must not open another through an alias.
def test_bind_alias_of_pii_is_refused_before_fuseki(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["fraudScore"])

    r = post(stack, PREFIX + "SELECT ?amount WHERE { ?c f:customerEmail ?e . BIND(?e AS ?amount) }")

    assert r.status_code == 400
    assert seen == []


# R2 regression: SERVICE must never reach another endpoint, under this product's grant.
def test_service_to_another_domain_is_refused_before_fuseki(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["customerName"])

    r = post(stack, PREFIX + "SELECT ?x WHERE { SERVICE <http://accounts-fuseki:3030/accounts/sparql> "
                            "{ ?c f:customerName ?x } }")

    assert r.status_code == 400
    assert seen == []


def test_unknown_predicate_is_refused(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["secretThing"])

    r = post(stack, PREFIX + "SELECT ?x WHERE { ?c f:secretThing ?x }")

    assert r.status_code == 400
    assert seen == []


def test_read_is_forwarded_and_pii_is_masked(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["customerEmail", "fraudScore"])

    r = post(stack, READ)

    assert r.status_code == 200
    assert len(seen) == 1
    binding = r.json()["results"]["bindings"][0]
    assert binding["email"]["type"] == "literal"
    assert binding["email"]["value"] != "john@acme.com"
    assert "@" not in binding["email"]["value"]  # pii floor: partial mask


def test_grant_for_one_predicate_does_not_read_another(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["fraudScore"])

    assert post(stack, READ).status_code == 403
    assert seen == []


def test_identity_in_the_body_is_ignored(sparql_stack):
    stack, seen = sparql_stack

    r = post(stack, READ, extra={"user_role": "fraud_analyst", "subject": "someone-else"})

    assert r.status_code == 403  # no grant; the body changed nothing
    assert seen == []
    assert stack.audit_records[-1]["roles"] == ["risk_analyst"]


def test_fuseki_outage_returns_503(sparql_stack):
    stack, seen = sparql_stack
    services = stack.boundary_app.state.services
    original = services.sparql_transport
    services.sparql_transport = httpx.MockTransport(lambda request: httpx.Response(500))
    grant(stack, ["customerEmail", "fraudScore"])
    try:
        r = post(stack, READ)
    finally:
        services.sparql_transport = original

    assert r.status_code == 503
    assert "results" not in r.json()


# R6 regression: a constant object or a FILTER on a PII predicate needs that predicate's grant, even though the
# query does not project it. Each request is refused before Fuseki sees it.
CONSTANT = PREFIX + 'SELECT ?score WHERE { ?c f:fraudScore ?score ; f:customerEmail "john@acme.com" }'
FILTERED = PREFIX + 'SELECT ?score WHERE { ?c f:fraudScore ?score ; f:customerEmail ?e . FILTER(STRSTARTS(?e, "j")) }'


def test_constant_object_on_pii_needs_the_pii_grant(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["fraudScore"])

    assert post(stack, CONSTANT).status_code == 403
    assert seen == []


def test_filter_on_pii_needs_the_pii_grant(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["fraudScore"])

    assert post(stack, FILTERED).status_code == 403
    assert seen == []


def test_constant_object_with_the_pii_grant_is_answered(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["fraudScore", "customerEmail"])

    assert post(stack, CONSTANT).status_code == 200
    assert len(seen) == 1


def test_variable_predicate_is_refused_before_fuseki(sparql_stack):
    stack, seen = sparql_stack
    grant(stack, ["customerEmail", "fraudScore"])

    assert post(stack, PREFIX + "SELECT ?v WHERE { ?c ?p ?v . ?c f:customerEmail ?e }").status_code == 400
    assert seen == []


def test_sparql_audit_records_the_query_hash_for_allowed_and_refused_reads(sparql_stack):
    import hashlib

    stack, _ = sparql_stack
    grant(stack, ["fraudScore"])
    post(stack, CONSTANT)  # refused: no PII grant
    refused = stack.audit_records[-1]
    expected = hashlib.sha256(CONSTANT.encode()).hexdigest()

    assert refused["decision"] == "deny"
    assert refused["query_sha256"] == expected
