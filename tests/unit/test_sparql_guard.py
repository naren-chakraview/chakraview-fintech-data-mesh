"""Read-only SPARQL: parse, don't regex, and classify by predicate, never by variable name.

The alias and scope cases here are the regression tests for review findings R1 and R2.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform"))
sys.path.insert(0, str(REPO))

from boundary.sparql import (QueryParseError, ReadOnlyViolation, parse_read_only,  # noqa: E402
                             projected_predicates)

PREFIX = "PREFIX f: <http://jena.apache.org/fintech#>\n"


@pytest.mark.parametrize("query", [
    PREFIX + 'INSERT DATA { <urn:x> f:customerEmail "a@b.c" }',
    PREFIX + "DELETE WHERE { ?s ?p ?o }",
    PREFIX + "DELETE { ?s ?p ?o } INSERT { ?s ?p 'x' } WHERE { ?s ?p ?o }",
    "LOAD <http://evil.example/data.ttl>",
    "CLEAR ALL",
    "DROP GRAPH <urn:g>",
    "CREATE GRAPH <urn:g>",
    "CLEAR DEFAULT; SELECT * WHERE { ?s ?p ?o }",
])
def test_update_forms_are_refused(query):
    with pytest.raises((ReadOnlyViolation, QueryParseError)):
        parse_read_only(query)


@pytest.mark.parametrize("query", [
    PREFIX + "ASK { ?c f:customerEmail ?e }",
    PREFIX + "CONSTRUCT { ?c f:customerEmail ?e } WHERE { ?c f:customerEmail ?e }",
    PREFIX + "DESCRIBE <urn:x>",
])
def test_non_select_forms_are_refused(query):
    with pytest.raises(ReadOnlyViolation):
        parse_read_only(query)


# R1: a variable's name never decides its classification. These routes used to leak an email.
@pytest.mark.parametrize("query", [
    PREFIX + "SELECT ?amount WHERE { ?c f:customerEmail ?e . BIND(?e AS ?amount) }",
    PREFIX + "SELECT (?e AS ?amount) WHERE { ?c f:customerEmail ?e }",
    PREFIX + "SELECT (MAX(?e) AS ?amount) WHERE { ?c f:customerEmail ?e }",
    PREFIX + "SELECT (GROUP_CONCAT(?e) AS ?amount) WHERE { ?c f:customerEmail ?e }",
    PREFIX + "SELECT ?amount WHERE { { SELECT ?e WHERE { ?c f:customerEmail ?e } } BIND(?e AS ?amount) }",
    PREFIX + "SELECT ?amount WHERE { ?c f:customerEmail ?e . VALUES ?amount { 'x' } }",
    PREFIX + "SELECT ?e WHERE { { SELECT ?e WHERE { ?c f:customerEmail ?e } } }",
])
def test_derivation_routes_are_refused(query):
    with pytest.raises(ReadOnlyViolation):
        parse_read_only(query)


# R2: no reaching another service, another graph, or a caller-chosen dataset.
@pytest.mark.parametrize("query", [
    PREFIX + "SELECT ?x WHERE { SERVICE <http://accounts-fuseki:3030/accounts/sparql> { ?c f:customerName ?x } }",
    PREFIX + "SELECT ?e WHERE { GRAPH <urn:accounts> { ?c f:customerEmail ?e } }",
    PREFIX + "SELECT ?e FROM <urn:accounts> WHERE { ?c f:customerEmail ?e }",
    PREFIX + "SELECT ?e FROM NAMED <urn:accounts> WHERE { GRAPH ?g { ?c f:customerEmail ?e } }",
])
def test_scope_escapes_are_refused(query):
    with pytest.raises(ReadOnlyViolation):
        parse_read_only(query)


def test_plain_select_is_allowed_and_classified_by_predicate():
    algebra = parse_read_only(PREFIX + "SELECT ?who ?score WHERE { ?c f:customerName ?who . ?c f:fraudScore ?score }")

    assert projected_predicates(algebra) == {"who": {"customerName"}, "score": {"fraudScore"}}


def test_optional_and_filter_are_allowed():
    parse_read_only(PREFIX + "SELECT ?e ?f WHERE { ?c f:customerEmail ?e OPTIONAL { ?c f:fraudScore ?f } FILTER(?f > 1) }")


def test_a_variable_bound_to_two_predicates_lists_both():
    algebra = parse_read_only(PREFIX + "SELECT ?v WHERE { ?c f:customerEmail ?v . ?d f:fraudScore ?v }")

    assert projected_predicates(algebra) == {"v": {"customerEmail", "fraudScore"}}


def test_select_star_is_refused_for_classification():
    algebra = parse_read_only(PREFIX + "SELECT * WHERE { ?c f:customerEmail ?e }")
    with pytest.raises(ReadOnlyViolation):
        projected_predicates(algebra)


def test_projected_variable_with_no_predicate_is_refused():
    algebra = parse_read_only(PREFIX + "SELECT ?c WHERE { ?c ?p ?o . ?x f:customerEmail ?e }")
    with pytest.raises(ReadOnlyViolation):
        projected_predicates(algebra)


def test_garbage_is_a_parse_error():
    with pytest.raises(QueryParseError):
        parse_read_only("this is not sparql at all")
