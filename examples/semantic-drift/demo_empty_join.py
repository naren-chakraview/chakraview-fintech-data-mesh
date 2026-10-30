"""D1: a query written from the published core returns zero rows, with no error.

Before: consumers were told to join on fintech:riskCustomer, but the producers
emit fintech:forCustomer. Their query silently matches nothing.
After: one core name (forCustomer) on both sides; the same join returns rows.
"""

from _loader import build_graphs, union

PREFIX = "PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>\n"

BEFORE_CONSUMER_QUERY = PREFIX + """
SELECT ?customerEmail ?riskScore WHERE {
  ?profile fintech:riskCustomer ?customer ;
           fintech:riskScore ?riskScore .
  ?customer fintech:customerEmail ?customerEmail .
  FILTER (?riskScore > 0.8)
}
"""

AFTER_CONSUMER_QUERY = PREFIX + """
SELECT ?customerEmail ?riskScore WHERE {
  ?profile fintech:forCustomer ?customer ;
           fintech:riskScore ?riskScore .
  ?customer fintech:customerEmail ?customerEmail .
  FILTER (?riskScore > 0.8)
}
"""


def show(label, query, graph):
    rows = list(graph.query(query))
    print(f"{label}: {len(rows)} row(s)")
    for row in rows:
        print(f"    customerEmail={row.customerEmail}  riskScore={row.riskScore}")


if __name__ == "__main__":
    print("D1 empty join\n")
    show("before, query written from the published core (riskCustomer)",
         BEFORE_CONSUMER_QUERY, union(build_graphs("before")))
    show("after, query written from the core 1.0.0 (forCustomer)",
         AFTER_CONSUMER_QUERY, union(build_graphs("after")))
