"""Direct writes: the contract, the classification of what is written, the RDF the shapes check, and the merge.

A product declares its write contract in its YAML (addendum W1):
    write_kind: captured | derived
    write_key:  the column that identifies a row
    write_mode: append | upsert   (append refuses a duplicate key; upsert replaces the row with that key)
    producers:  the SPIFFE IDs of the services that may write it directly (derived, confidential or personal)

What is written decides the gate, not the product's most sensitive column alone: the effective classification is the
highest classification among the columns in the write, and a column with no classification counts as personal (fail
closed, addendum W1).
"""

from typing import Iterable, List

from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import XSD

from shared.governance.products import CLASSIFICATION_ORDER, column_classifications

FINTECH = Namespace("https://chakracommerce.com/ontology/fintech/")
MAX_ROWS = 50

# The shape class and the predicate of each column, for the products that accept direct writes.
SHAPE_CLASS = {
    "accounts.customer-intake": "CustomerIntake",
    "risk-compliance.score-freshness-summary": "ScoreFreshnessSummary",
    "risk-compliance.risk-scores": "RiskScoreWrite",
}
PREDICATE = {
    "accounts.customer-intake": {"customer_iri": "customerIri", "legal_name": "legalName", "ssn": "ssn",
                                 "address": "address"},
    "risk-compliance.score-freshness-summary": {"summary_id": "summaryId", "day": "day", "risk_band": "riskBand",
                                                "stale_count": "staleCount", "customer_label": "customerLabel"},
    "risk-compliance.risk-scores": {"account_ref": "accountRef", "fraud_score": "fraudScore",
                                    "risk_band": "riskBand", "kyc_verdict": "kycVerdict",
                                    "customer_iri": "customerIri", "scored_at": "scoredAt"},
}
DATATYPE = {"stale_count": XSD.integer, "fraud_score": XSD.decimal}
# A column whose value is an identifier, held as an IRI node (the shapes check it as one).
IRI_COLUMNS = {"customer_iri"}


class WriteContractError(Exception):
    """The product has no write contract, or the write does not match it. The caller answers 422."""


class WriteConflict(Exception):
    """The write is valid, but it duplicates a key the product already holds (append). The caller answers 409."""


def subjects(rows: List[dict], key: str = "customer_iri") -> set:
    """The data subjects the rows describe: the distinct customer identifiers. A row with none adds nothing."""
    return {row.get(key) for row in rows if row.get(key)}


def contract(product: dict) -> dict:
    kind = product.get("write_kind")
    if kind not in ("captured", "derived"):
        raise WriteContractError("product has no write contract")
    mode = product.get("write_mode", "append")
    if mode not in ("append", "upsert"):
        raise WriteContractError("write_mode must be append or upsert")
    key = product.get("write_key")
    if not key:
        raise WriteContractError("product declares no write_key")
    return {"kind": kind, "key": key, "mode": mode, "producers": list(product.get("producers") or []),
            "subject_consent": bool(product.get("subject_consent", False))}


def effective_classification(product: dict, columns: Iterable[str]) -> str:
    """The highest classification among the written columns. A column with no classification is personal."""
    declared = column_classifications(product)
    levels = [declared.get(column, "pii") for column in columns]
    if not levels:
        raise WriteContractError("a write names no columns")
    return max(levels, key=CLASSIFICATION_ORDER.index)


def complete(row: dict, columns: List[str]) -> dict:
    """A row with every contract column present; a column the caller left out is stored as null."""
    return {column: row.get(column) for column in columns}


def rows_to_graph(product_id: str, rows: List[dict]) -> Graph:
    """One node per row, typed for the product's shapes, so the shapes check exactly what is written."""
    graph = Graph()
    cls = SHAPE_CLASS[product_id]
    predicates = PREDICATE[product_id]
    for row in rows:
        node = BNode()
        graph.add((node, RDF.type, FINTECH[cls]))
        for column, value in row.items():
            if value is None or column not in predicates:
                continue
            if column in IRI_COLUMNS:
                obj = URIRef(str(value))
            elif column in DATATYPE:
                obj = Literal(str(value), datatype=DATATYPE[column])
            else:
                obj = Literal(str(value))  # a plain string, which is what the shapes' enumerations compare with
            graph.add((node, FINTECH[predicates[column]], obj))
    return graph


def merge(current: List[dict], new: List[dict], key: str, mode: str) -> List[dict]:
    """The product's complete new state. Append refuses a key already held or repeated in the write."""
    by_key = {row[key]: row for row in current}
    if mode == "append":
        seen = set()
        for row in new:
            value = row[key]
            if value in by_key or value in seen:
                raise WriteConflict(f"{key} {value!r} already exists in the product")
            seen.add(value)
        by_key.update({row[key]: row for row in new})
    else:
        by_key.update({row[key]: row for row in new})
    return sorted(by_key.values(), key=lambda row: str(row[key]))
