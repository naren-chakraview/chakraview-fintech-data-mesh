"""Contract test: each domain's real producer output conforms to its shapes."""

import pytest

from shared.semantic.validation import validate_graph


@pytest.mark.parametrize("domain", ["accounts", "transactions"])
def test_producer_output_conforms(domain, domain_graphs):
    conforms, _, report = validate_graph(domain_graphs[domain], domain)
    assert conforms, report


def test_risk_output_conforms(domain_graphs):
    conforms, _, report = validate_graph(domain_graphs["risk"], "risk-compliance")
    assert conforms, report
