"""Shared fixtures for contract tests.

Each domain's semantic package is named `semantic`, so the three packages
cannot be imported side by side. They are loaded here by file path under
unique module names instead.
"""

import importlib.util
from datetime import datetime

import pandas as pd
import pytest
from rdflib import Graph

from shared.semantic.paths import CORE_ONTOLOGY_PATH, REPO_ROOT

SEMANTIC_DIRS = {
    "accounts": REPO_ROOT / "domains/accounts/src/main/python/semantic",
    "risk": REPO_ROOT / "domains/risk-compliance/src/main/python/semantic",
    "transactions": REPO_ROOT / "domains/transactions/src/main/python/semantic",
}


def load_module(unique_name, path):
    spec = importlib.util.spec_from_file_location(unique_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def domain_resolver_classes():
    """IRI resolver classes exactly as each domain ships them."""
    return {
        "accounts": load_module(
            "contract_accounts_iri", SEMANTIC_DIRS["accounts"] / "iri_resolver.py"
        ).IriResolver,
        "risk": load_module(
            "contract_risk_cross", SEMANTIC_DIRS["risk"] / "cross_domain_resolver.py"
        ).CrossDomainResolver,
        "transactions": load_module(
            "contract_txn_cross", SEMANTIC_DIRS["transactions"] / "cross_domain_resolver.py"
        ).CrossDomainResolver,
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


@pytest.fixture(scope="session")
def domain_graphs(domain_resolver_classes):
    """Real producer output from each domain, run on the same customers.

    Keys: 'accounts', 'risk', 'transactions'. Each value is an rdflib Graph.
    """
    accounts_mod = load_module("contract_accounts_s2r", SEMANTIC_DIRS["accounts"] / "silver_to_rdf.py")
    risk_mod = load_module("contract_risk_s2r", SEMANTIC_DIRS["risk"] / "silver_to_rdf.py")
    txn_mod = load_module("contract_txn_s2r", SEMANTIC_DIRS["transactions"] / "silver_to_rdf.py")
    iri_modules = {
        "accounts": load_module("contract_accounts_iri_mod", SEMANTIC_DIRS["accounts"] / "iri_resolver.py"),
        "risk": load_module("contract_risk_iri_mod", SEMANTIC_DIRS["risk"] / "iri_resolver.py"),
        "transactions": load_module("contract_txn_iri_mod", SEMANTIC_DIRS["transactions"] / "iri_resolver.py"),
    }
    ontology = str(CORE_ONTOLOGY_PATH)
    resolvers = {name: mod.IriResolver() for name, mod in iri_modules.items()}
    cross = {name: cls() for name, cls in domain_resolver_classes.items()}

    accounts = accounts_mod.SilverToRdfTransformer(resolvers["accounts"], ontology)
    accounts.transform_customers_to_rdf(CUSTOMERS)
    accounts.transform_accounts_to_rdf(ACCOUNTS, CUSTOMERS)

    risk = risk_mod.SilverToRdfTransformer(resolvers["risk"], cross["risk"], ontology)
    risk.transform_risk_profiles_to_rdf(RISK)

    txn = txn_mod.SilverToRdfTransformer(resolvers["transactions"], cross["transactions"], ontology)
    txn.transform_transactions_to_rdf(TRANSACTIONS)

    return {
        "accounts": accounts.get_graph(),
        "risk": risk.get_graph(),
        "transactions": txn.get_graph(),
    }
