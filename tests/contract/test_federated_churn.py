"""Contract test: the federated churn query returns the known high-risk customer.

The three domain graphs come from real producer output (see conftest.py).
SERVICE clauses are rewritten to GRAPH clauses so the query runs locally
against named graphs. John is the only customer with a failed transaction
after 2026-04-30 and a risk score above 0.8, so he must be the only row.
"""

import re

from rdflib import Dataset, URIRef

from shared.semantic.identity import mint_customer_iri
from shared.semantic.paths import REPO_ROOT

QUERY_PATH = REPO_ROOT / "domains/federation/queries/churn-analysis-federated.sparql"
SERVICE_GRAPHS = {
    "accounts": "urn:graph:accounts",
    "transactions": "urn:graph:transactions",
    "risk": "urn:graph:risk",
}


def rewrite_services(text):
    def to_graph(match):
        url = match.group(1)
        for domain, graph in SERVICE_GRAPHS.items():
            if domain in url:
                return f"GRAPH <{graph}>"
        raise AssertionError(f"SERVICE endpoint not mapped to a fixture graph: {url}")

    return re.sub(r"SERVICE\s*<([^>]+)>", to_graph, text)


def run_federated(query_text, domain_graphs):
    dataset = Dataset()
    for domain, graph in SERVICE_GRAPHS.items():
        context = dataset.graph(URIRef(graph))
        for triple in domain_graphs[domain]:
            context.add(triple)
    return list(dataset.query(rewrite_services(query_text)))


def test_query_selects_only_variables_it_binds():
    text = QUERY_PATH.read_text(encoding="utf-8")
    select_clause = re.search(r"SELECT(.*?)WHERE", text, re.S | re.I).group(1)
    # Plain selected variables; aliases from "(... AS ?alias)" are bound by the aggregate.
    selected = re.findall(r"(?<!AS )\?(\w+)", select_clause)
    where_body = text[text.index("WHERE"):]
    for var in selected:
        assert f"?{var}" in where_body, f"?{var} is selected but never bound"


def test_known_high_risk_customer_is_returned(domain_graphs):
    rows = run_federated(QUERY_PATH.read_text(encoding="utf-8"), domain_graphs)
    john = mint_customer_iri("john@acme.com", "kyc_9999", key="test-only-iri-key-do-not-use-in-production")
    assert len(rows) == 1
    assert str(rows[0].customer) == john
    assert str(rows[0].name) == "John Doe"
