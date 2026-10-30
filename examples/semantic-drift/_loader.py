"""Loads the frozen "before" producers and the current "after" producers.

The before code lives in examples/semantic-drift/before/ (frozen from commit
44f2cba, tag semantic-drift-before). The after code is the live domain code.
Both are loaded by file path under unique names, because every domain's
package is called `semantic`.
"""

import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from rdflib import Graph

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
BEFORE_ROOT = HERE / "before"

# Demo-only key. Real runs must set FINTECH_IRI_KEY themselves.
os.environ.setdefault("FINTECH_IRI_KEY", "demo-only-key-not-for-production")
sys.path.insert(0, str(REPO_ROOT))

from shared.semantic.paths import CORE_ONTOLOGY_PATH  # noqa: E402

BEFORE_ONTOLOGY = BEFORE_ROOT / "docs/case-study/fintech-semantic-integration/shared-ontology.ttl"

SEMANTIC_DIR = {
    "accounts": "domains/accounts/src/main/python/semantic",
    "risk": "domains/risk-compliance/src/main/python/semantic",
    "transactions": "domains/transactions/src/main/python/semantic",
}

CUSTOMERS = pd.DataFrame({
    'email': ['john@acme.com', 'jane@acme.com', 'bob@widgets.com'],
    'kyc_id': ['kyc_9999', 'kyc_8888', 'kyc_7777'],
    'name': ['John Doe', 'Jane Roe', 'Bob Stone'],
    'status': ['active', 'active', 'active'],
})
ACCOUNTS = pd.DataFrame({
    'account_id': ['acc_001', 'acc_002'],
    'customer_email': ['john@acme.com', 'jane@acme.com'],
    'customer_kyc_id': ['kyc_9999', 'kyc_8888'],
    'balance': [1200.50, 300.00],
    'status': ['active', 'active'],
    'account_type': ['checking', 'savings'],
})
TRANSACTIONS = pd.DataFrame({
    'transaction_id': ['txn_001', 'txn_002', 'txn_003'],
    'customer_email': ['john@acme.com', 'jane@acme.com', 'bob@widgets.com'],
    'customer_kyc_id': ['kyc_9999', 'kyc_8888', 'kyc_7777'],
    'counterparty_id': ['stripe', 'paypal', 'square'],
    'amount': [2500.00, 1500.00, 500.00],
    'status': ['failed', 'executed', 'executed'],
    'transaction_date': ['2026-05-24T08:00:00Z', '2026-05-22T14:30:00Z', '2026-05-20T10:15:00Z'],
})
RISK = pd.DataFrame({
    'risk_id': ['risk_001', 'risk_002', 'risk_003'],
    'customer_email': ['john@acme.com', 'jane@acme.com', 'bob@widgets.com'],
    'customer_kyc_id': ['kyc_9999', 'kyc_8888', 'kyc_7777'],
    'risk_score': [0.92, 0.45, 0.78],
    'risk_level': ['HIGH', 'LOW', 'MEDIUM'],
    'compliance_status': ['UNDER_REVIEW', 'COMPLIANT', 'NON_COMPLIANT'],
    'kyc_status': ['VERIFIED', 'VERIFIED', 'IN_PROGRESS'],
    'fraud_flags_count': [2, 0, 1],
    'last_review_date': [datetime(2026, 5, 20, 14, 30), datetime(2026, 5, 15, 10, 0),
                         datetime(2026, 5, 25, 16, 45)],
    'next_review_date': [datetime(2026, 8, 20), datetime(2026, 8, 15), datetime(2026, 8, 25)],
    'review_notes': ['Pending docs', 'None', 'Follow up'],
})


def _load(unique_name, path):
    spec = importlib.util.spec_from_file_location(unique_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_module(version, domain, module):
    """version is 'before' or 'after'; module is e.g. 'silver_to_rdf'."""
    root = BEFORE_ROOT if version == "before" else REPO_ROOT
    return _load(f"{version}_{domain}_{module}", root / SEMANTIC_DIR[domain] / f"{module}.py")


def build_graphs(version):
    """Run each domain's producer on the same sample data. Returns {domain: Graph}."""
    ontology = str(BEFORE_ONTOLOGY if version == "before" else CORE_ONTOLOGY_PATH)
    iri = {d: load_module(version, d, "iri_resolver").IriResolver() for d in SEMANTIC_DIR}
    cross = {
        d: load_module(version, d, "cross_domain_resolver").CrossDomainResolver()
        for d in ("risk", "transactions")
    }

    accounts = load_module(version, "accounts", "silver_to_rdf").SilverToRdfTransformer(
        iri["accounts"], ontology)
    accounts.transform_customers_to_rdf(CUSTOMERS)
    accounts.transform_accounts_to_rdf(ACCOUNTS, CUSTOMERS)

    risk = load_module(version, "risk", "silver_to_rdf").SilverToRdfTransformer(
        iri["risk"], cross["risk"], ontology)
    risk.transform_risk_profiles_to_rdf(RISK)

    txn = load_module(version, "transactions", "silver_to_rdf").SilverToRdfTransformer(
        iri["transactions"], cross["transactions"], ontology)
    txn.transform_transactions_to_rdf(TRANSACTIONS)

    return {"accounts": accounts.get_graph(), "risk": risk.get_graph(),
            "transactions": txn.get_graph()}


def union(graphs):
    merged = Graph()
    for g in graphs.values():
        merged += g
    return merged
