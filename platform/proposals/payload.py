"""Parse and validate a proposal payload. Fail closed: a payload that does not conform is never recorded."""

from typing import List

from rdflib import RDF, Graph, Namespace

from shared.semantic.validation import validate_graph, violation_messages

FINTECH = Namespace("https://chakracommerce.com/ontology/fintech/")
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_TRIPLES = 500
MAX_NOTES = 20
FORMATS = {"turtle": "turtle", "json-ld": "json-ld"}


class PayloadError(Exception):
    """The payload is refused. status is the HTTP status; detail names what failed, never the data."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def parse_payload(payload: bytes, fmt: str) -> Graph:
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise PayloadError(413, f"payload is larger than {MAX_PAYLOAD_BYTES} bytes")
    if fmt not in FORMATS:
        raise PayloadError(400, "format must be turtle or json-ld")
    graph = Graph()
    try:
        graph.parse(data=payload.decode("utf-8"), format=FORMATS[fmt])
    except Exception as exc:  # rdflib raises several parser errors; all mean "not a payload we accept"
        raise PayloadError(422, f"payload does not parse as {fmt}") from exc
    if len(graph) > MAX_TRIPLES:
        raise PayloadError(413, f"payload has more than {MAX_TRIPLES} triples")
    return graph


def validate_payload(graph: Graph) -> None:
    """SHACL: the core shapes (shared with the producers) and the review-note shape. Any violation refuses."""
    conforms, report_graph, report = validate_graph(graph, "risk-review-notes")
    if not conforms:
        messages = violation_messages(report_graph)
        raise PayloadError(422, "payload does not conform to the semantic shapes: " + "; ".join(messages or [report]))
    notes = list(graph.subjects(RDF.type, FINTECH.ReviewNote))
    if not notes:
        raise PayloadError(422, "payload contains no fintech:ReviewNote")
    if len(notes) > MAX_NOTES:
        raise PayloadError(413, f"payload has more than {MAX_NOTES} review notes")


def review_note_rows(graph: Graph) -> List[dict]:
    """The rows an accepted note adds to the product. Derived from the graph, never from the payload text."""
    rows = []
    for note in graph.subjects(RDF.type, FINTECH.ReviewNote):
        rows.append({
            "note_id": _one(graph, note, FINTECH.noteId),
            "customer_iri": _one(graph, note, FINTECH.forCustomer),
            "risk_band": _one(graph, note, FINTECH.riskBand),
            "reviewed_note": _one(graph, note, FINTECH.reviewedNote),
        })
    return sorted(rows, key=lambda row: row["note_id"])


def _one(graph: Graph, subject, predicate) -> str:
    value = graph.value(subject, predicate)
    if value is None:
        raise PayloadError(422, f"review note is missing {predicate.split('/')[-1]}")
    return str(value)
