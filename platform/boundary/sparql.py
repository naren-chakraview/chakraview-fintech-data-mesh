"""Read-only SPARQL. Parse, don't regex: a query is refused if it parses as an update, or does not parse as a query form."""

from typing import Set

import httpx
from rdflib.plugins.sparql import parser as sparql_parser
from rdflib.plugins.sparql.algebra import translateQuery, traverse
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.term import Variable

READ_FORMS = {"SelectQuery", "AskQuery", "ConstructQuery", "DescribeQuery"}

# Predicates whose object values are personal data. A variable bound to one of these is PII.
PII_PREDICATE_NAMES = {"customerName", "customerEmail", "accountId", "accountIdentifier"}


class ReadOnlyViolation(Exception):
    """The query would change data, or is not a read form."""


class QueryParseError(Exception):
    """The query text is not valid SPARQL."""


class UpstreamError(Exception):
    """Fuseki did not answer with results. The caller must return no data."""


def parse_read_only(query: str) -> CompValue:
    """Return the translated query algebra for a read-only query. Raises ReadOnlyViolation or QueryParseError."""
    try:
        sparql_parser.parseUpdate(query)
    except Exception:
        pass
    else:
        raise ReadOnlyViolation("update forms are not allowed on the read path")

    try:
        parsed = sparql_parser.parseQuery(query)
        translated = translateQuery(parsed)
    except Exception as exc:
        raise QueryParseError("not valid SPARQL") from exc

    form = translated.algebra.name
    if form not in READ_FORMS:
        raise ReadOnlyViolation(f"query form {form} is not a read")
    return translated.algebra


def pii_variables(algebra: CompValue) -> Set[str]:
    """Variables bound to a PII predicate in any triple pattern: ?s :customerEmail ?email binds email."""
    found: Set[str] = set()

    def visit(node):
        if getattr(node, "name", None) == "BGP":
            for _, predicate, obj in node.triples:
                local = str(predicate).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                if local in PII_PREDICATE_NAMES and isinstance(obj, Variable):
                    found.add(str(obj))
        return node

    traverse(algebra, visitPost=visit)
    return found


async def forward_read(endpoint: str, query: str, *, transport=None) -> dict:
    """Send a read-only query to the domain's Fuseki query endpoint and return the JSON results."""
    try:
        async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
            response = await client.post(
                endpoint,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
    except httpx.HTTPError as exc:
        raise UpstreamError(f"SPARQL endpoint unreachable: {exc}") from exc
    if response.status_code != 200:
        raise UpstreamError(f"SPARQL endpoint returned HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamError("SPARQL endpoint returned non-JSON") from exc
