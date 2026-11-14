"""Read-only SPARQL for the boundary.

Three rules, all enforced on the parsed query, never by regex:

1. Only SELECT is allowed. ASK, CONSTRUCT and DESCRIBE are refused: they return booleans or triples
   without the per-variable checks below.
2. Only plain graph patterns are allowed. Anything that can create a value, move to another graph, or reach
   another service is refused by its algebra node: BIND and projection expressions (Extend), aggregates
   (Group, AggregateJoin), subqueries and VALUES (ToMultiSet, values), GRAPH, SERVICE, and FROM/FROM NAMED
   (DatasetClause). Update forms are refused first.
3. Every projected variable must trace to the object of a triple pattern whose predicate is a known column
   or a PII predicate. The classification of a variable comes from that predicate, not from its name.
"""

from typing import Dict, Set

import httpx
from rdflib.plugins.sparql import parser as sparql_parser
from rdflib.plugins.sparql.algebra import translateQuery, traverse
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.paths import Path as PropertyPath
from rdflib.term import Variable

# Predicates whose object values are personal data.
PII_PREDICATE_NAMES = {"customerName", "customerEmail", "accountId", "accountIdentifier"}

# Algebra nodes that can create a value, change graph, or reach another service. Refused by name.
REFUSED_NODES = {
    "Extend",            # BIND and (expr AS ?v) in a projection
    "Group",             # GROUP BY
    "AggregateJoin",     # COUNT, SUM, MAX, GROUP_CONCAT, SAMPLE, ...
    "ToMultiSet",        # subqueries and VALUES blocks
    "values",            # inline VALUES data
    "Graph",             # GRAPH <g> { ... }
    "ServiceGraphPattern",  # SERVICE <endpoint> { ... }
    "DatasetClause",     # FROM and FROM NAMED
}


class ReadOnlyViolation(Exception):
    """The query would change data, or uses a form the boundary does not allow."""


class QueryParseError(Exception):
    """The query text is not valid SPARQL."""


class UpstreamError(Exception):
    """Fuseki did not answer with results. The caller must return no data."""


def _local_name(iri) -> str:
    return str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _walk(algebra: CompValue):
    seen = []

    def visit(node):
        if isinstance(node, CompValue):
            seen.append(node)
        return node

    traverse(algebra, visitPost=visit)
    return seen


def parse_read_only(query: str) -> CompValue:
    """Return the translated algebra of a read-only SELECT. Raises ReadOnlyViolation or QueryParseError."""
    try:
        sparql_parser.parseUpdate(query)
    except Exception:
        pass
    else:
        raise ReadOnlyViolation("update forms are not allowed on the read path")

    try:
        translated = translateQuery(sparql_parser.parseQuery(query))
    except Exception as exc:
        raise QueryParseError("not valid SPARQL") from exc

    algebra = translated.algebra
    if algebra.name != "SelectQuery":
        raise ReadOnlyViolation(f"only SELECT is allowed; got {algebra.name}")

    refused = sorted({node.name for node in _walk(algebra)} & REFUSED_NODES)
    if refused:
        raise ReadOnlyViolation(f"not allowed on the read path: {', '.join(refused)}")
    pattern_predicates(algebra)  # refuses variable predicates and property paths
    return algebra


def pattern_predicates(algebra: CompValue) -> Set[str]:
    """Every predicate local name in every triple pattern, whether projected, filtered, constant or not.

    A pattern whose predicate is a variable or a property path could reach any predicate, so it is refused.
    """
    predicates: Set[str] = set()
    for node in _walk(algebra):
        if node.name == "BGP":
            for _, predicate, _ in node.triples:
                if isinstance(predicate, (Variable, PropertyPath)):
                    raise ReadOnlyViolation("variable predicates and property paths are not allowed")
                predicates.add(_local_name(predicate))
    return predicates


def projected_predicates(algebra: CompValue) -> Dict[str, Set[str]]:
    """Projected variable -> the predicate local names its value is read from.

    A variable is classified by where its value comes from. A variable with no triple-pattern origin
    (for example one that is never bound by a triple) is refused, because nothing can classify it.
    """
    origins: Dict[str, Set[str]] = {}
    for node in _walk(algebra):
        if node.name == "BGP":
            for _, predicate, obj in node.triples:
                if isinstance(obj, Variable):
                    origins.setdefault(str(obj), set()).add(_local_name(predicate))

    projected = [str(v) for v in (algebra.get("PV") or [])]
    if not projected:
        raise ReadOnlyViolation("SELECT * is not allowed; name the columns you need")
    result: Dict[str, Set[str]] = {}
    for variable in projected:
        if variable not in origins:
            raise ReadOnlyViolation(f"?{variable} is not bound to a predicate; it cannot be classified")
        result[variable] = origins[variable]
    return result


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
