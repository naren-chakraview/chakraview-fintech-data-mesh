"""Read-only SPARQL: parse, don't regex. Update forms and non-read forms never reach Fuseki."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform"))
sys.path.insert(0, str(REPO))

from boundary.sparql import QueryParseError, ReadOnlyViolation, parse_read_only, pii_variables  # noqa: E402

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


def test_update_is_always_read_only_violation_not_parse_error():
    with pytest.raises(ReadOnlyViolation):
        parse_read_only(PREFIX + 'INSERT DATA { <urn:x> f:customerEmail "a@b.c" }')


@pytest.mark.parametrize("query", [
    PREFIX + "SELECT ?email WHERE { ?c f:customerEmail ?email }",
    PREFIX + "ASK { ?s ?p ?o }",
    PREFIX + "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    PREFIX + "DESCRIBE <urn:x>",
])
def test_read_forms_parse(query):
    parse_read_only(query)


def test_garbage_is_a_parse_error():
    with pytest.raises(QueryParseError):
        parse_read_only("this is not sparql at all")


def test_pii_variables_follow_the_predicate_not_the_name():
    algebra = parse_read_only(
        PREFIX + "SELECT ?who ?mail ?score WHERE { ?c f:customerEmail ?mail . ?c f:customerName ?who . ?c f:fraudScore ?score }"
    )

    assert pii_variables(algebra) == {"mail", "who"}
