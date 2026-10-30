"""Producer-side SHACL validation.

A producer's graph must conform to the core shapes and its domain's shapes
before anything is written. A violation raises SemanticValidationError with
a readable report, so the job fails instead of publishing drifted triples.
"""

from typing import Tuple

from pyshacl import validate
from rdflib import Graph
from rdflib.namespace import SH

from shared.semantic.paths import SHAPES_DIR

DOMAIN_SHAPES = {
    "accounts": "accounts-shapes.ttl",
    "risk-compliance": "risk-compliance-shapes.ttl",
    "transactions": "transactions-shapes.ttl",
}


class SemanticValidationError(ValueError):
    """Raised when a producer's graph does not conform to the shapes."""

    def __init__(self, domain: str, report: str):
        self.domain = domain
        self.report = report
        super().__init__(f"{domain} output does not conform to the semantic shapes:\n{report}")


def load_shapes(domain: str) -> Graph:
    """Load core shapes plus the shapes owned by one domain."""
    shapes = Graph()
    shapes.parse(SHAPES_DIR / "core-shapes.ttl", format="turtle")
    shapes.parse(SHAPES_DIR / DOMAIN_SHAPES[domain], format="turtle")
    return shapes


def validate_graph(data: Graph, domain: str) -> Tuple[bool, Graph, str]:
    """Validate a producer graph. Returns (conforms, report_graph, report_text)."""
    conforms, report_graph, report_text = validate(
        data,
        shacl_graph=load_shapes(domain),
        inference="none",
        abort_on_first=False,
        meta_shacl=False,
        advanced=True,
    )
    return conforms, report_graph, report_text


def assert_conforms(data: Graph, domain: str) -> None:
    """Raise SemanticValidationError unless the graph conforms."""
    conforms, _, report_text = validate_graph(data, domain)
    if not conforms:
        raise SemanticValidationError(domain, report_text)


def violation_messages(report_graph: Graph) -> list:
    """One message per violation, for readable demo and log output."""
    messages = []
    for result in report_graph.subjects(predicate=None, object=SH.ValidationResult):
        message = report_graph.value(result, SH.resultMessage)
        focus = report_graph.value(result, SH.focusNode)
        path = report_graph.value(result, SH.resultPath)
        messages.append(f"{focus} [{path}]: {message}")
    return messages
