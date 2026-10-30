"""Negative contract tests: each drift the brief names must fail validation.

Each graph below is the smallest one that breaks exactly one rule.
"""

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from shared.semantic.validation import SemanticValidationError, assert_conforms, validate_graph

FINTECH = Namespace("https://chakracommerce.com/ontology/fintech/")
GOOD_CUSTOMER = URIRef("https://chakracommerce.com/customer#" + "a" * 64)


def base_account(graph, account="acc_1", balance=Literal("10.00", datatype=XSD.decimal)):
    acc = URIRef(f"https://chakracommerce.com/account#{account}")
    graph.add((acc, RDF.type, FINTECH.Account))
    graph.add((acc, FINTECH.accountId, Literal(account)))
    graph.add((acc, FINTECH.accountBalance, balance))
    graph.add((acc, FINTECH.accountOwner, GOOD_CUSTOMER))
    graph.add((acc, FINTECH.sourceSystem, Literal("accounts")))
    graph.add((acc, FINTECH.sourceIngestionTime,
               Literal("2026-10-29T00:00:00", datatype=XSD.dateTime)))
    return acc


def test_clean_account_conforms():
    g = Graph()
    base_account(g)
    conforms, _, report = validate_graph(g, "accounts")
    assert conforms, report


def test_drifted_8_hex_customer_iri_is_rejected():
    g = Graph()
    base_account(g)
    short = URIRef("https://chakracommerce.com/customer#15e5a0c2")
    g.add((short, RDF.type, FINTECH.Customer))
    g.add((short, FINTECH.sourceSystem, Literal("accounts")))
    g.add((short, FINTECH.sourceIngestionTime, Literal("2026-10-29T00:00:00", datatype=XSD.dateTime)))
    conforms, _, _ = validate_graph(g, "accounts")
    assert not conforms


def test_float_or_undefined_decimal_balance_is_rejected():
    g = Graph()
    base_account(g, balance=Literal("10.0", datatype=FINTECH.decimal))
    conforms, _, _ = validate_graph(g, "accounts")
    assert not conforms


def test_deprecated_risk_customer_link_is_rejected():
    g = Graph()
    profile = URIRef("https://chakracommerce.com/risk-profile#risk_1")
    g.add((profile, RDF.type, FINTECH.RiskProfile))
    g.add((profile, FINTECH.riskScore, Literal("0.9", datatype=XSD.decimal)))
    g.add((profile, FINTECH.forCustomer, GOOD_CUSTOMER))
    g.add((profile, FINTECH.riskCustomer, GOOD_CUSTOMER))
    g.add((profile, FINTECH.sourceSystem, Literal("risk_compliance")))
    g.add((profile, FINTECH.sourceIngestionTime, Literal("2026-10-29T00:00:00", datatype=XSD.dateTime)))
    conforms, _, report = validate_graph(g, "risk-compliance")
    assert not conforms
    assert "riskCustomer" in report


def test_missing_provenance_is_rejected():
    g = Graph()
    base_account(g)
    acc = next(g.subjects(RDF.type, FINTECH.Account))
    g.remove((acc, FINTECH.sourceSystem, None))
    conforms, _, _ = validate_graph(g, "accounts")
    assert not conforms


def test_assert_conforms_raises_with_report():
    g = Graph()
    base_account(g, balance=Literal("10.0", datatype=FINTECH.decimal))
    with pytest.raises(SemanticValidationError) as exc:
        assert_conforms(g, "accounts")
    assert "accounts output does not conform" in str(exc.value)
