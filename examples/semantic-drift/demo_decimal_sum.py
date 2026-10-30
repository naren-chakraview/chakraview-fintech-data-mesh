"""D6: amounts typed as an undefined datatype cannot be summed.

Before: amounts are typed fintech:decimal (defined nowhere) and built from
float, so SUM fails. After: xsd:decimal built from Decimal, so SUM works.
"""

from _loader import build_graphs

QUERY = """
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
SELECT (SUM(?amount) AS ?total) WHERE {
  ?txn fintech:transactionAmount ?amount .
}
"""


def run_sum(label, graph):
    print(f"{label}")
    try:
        rows = list(graph.query(QUERY))
    except Exception as error:  # rdflib raises on non-numeric SUM inputs
        print(f"  error: {type(error).__name__}: {error}")
        return
    total = rows[0].total if rows else None
    if total is None:
        print("  total: unbound (SUM produced no value, and nothing failed loudly)")
    else:
        print(f"  total: {total}")


if __name__ == "__main__":
    print("D6 numbers that are not numbers\n")
    before_txn = build_graphs("before")["transactions"]
    after_txn = build_graphs("after")["transactions"]
    run_sum("before, amounts typed fintech:decimal:", before_txn)
    run_sum("after, amounts typed xsd:decimal:", after_txn)
