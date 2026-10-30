"""D1, D4, D6: the shapes catch what the drifted producers emitted.

Before output is validated against the current shapes. Violations are grouped
by the drift they show, one line per drift.
"""

from collections import OrderedDict

from _loader import build_graphs
from shared.semantic.validation import validate_graph, violation_messages

DOMAIN_FOR = {"accounts": "accounts", "risk": "risk-compliance", "transactions": "transactions"}

DRIFT_NOTES = OrderedDict([
    ("D1", "deprecated link name in use"),
    ("D4", "customer IRI is not the 64-hex identity-library digest"),
    ("D6", "amount or date not typed xsd:decimal / xsd:dateTime"),
    ("other", "other shape violation"),
])


def label_for(message):
    if "deprecated" in message:
        return "D1"
    if "IRI" in message:
        return "D4"
    if "decimal" in message or "dateTime" in message:
        return "D6"
    return "other"


def check(version):
    """Return (conforms, {label: [messages]}) for every domain's output."""
    grouped = {label: [] for label in DRIFT_NOTES}
    conforms_all = True
    for domain, graph in build_graphs(version).items():
        conforms, report_graph, _ = validate_graph(graph, DOMAIN_FOR[domain])
        conforms_all = conforms_all and conforms
        for message in violation_messages(report_graph):
            grouped[label_for(message)].append(f"{domain}: {message}")
    return conforms_all, grouped


if __name__ == "__main__":
    print("Before output against the shapes (one line per drift):")
    before_ok, before_groups = check("before")
    for label, note in DRIFT_NOTES.items():
        found = before_groups[label]
        if not found:
            if label == "D1":
                print(f"  [D1] 0 violations: producers emitted fintech:forCustomer, "
                      f"so the drift lived in the published core and consumer queries "
                      f"(see demo_empty_join.py)")
            continue
        print(f"  [{label}] {len(found)} violation(s), {note}. e.g. {found[0]}")
    print(f"  Conforms: {before_ok}\n")

    print("After output against the shapes:")
    after_ok, _ = check("after")
    print(f"  Conforms: {after_ok}")
