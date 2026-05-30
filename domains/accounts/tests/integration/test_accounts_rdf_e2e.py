import pytest
import pandas as pd
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src' / 'main' / 'python'))

from semantic.iri_resolver import IriResolver
from semantic.silver_to_rdf import SilverToRdfTransformer
from rdflib import RDF


class TestAccountsRdfE2E:
    """End-to-end integration test: Silver CSV → IRI minting → RDF → SPARQL"""

    @pytest.fixture
    def sample_customers_df(self):
        """Sample customer data (Silver table)"""
        return pd.DataFrame({
            'customer_id': ['cust_001', 'cust_002', 'cust_003'],
            'email': ['john@acme.com', 'jane@techcorp.io', 'bob@widgets.com'],
            'kyc_id': ['kyc_9999', 'kyc_8888', 'kyc_7777'],
            'name': ['John Doe', 'Jane Smith', 'Bob Wilson'],
            'status': ['active', 'active', 'suspended']
        })

    @pytest.fixture
    def sample_accounts_df(self):
        """Sample account data (Silver table)"""
        return pd.DataFrame({
            'account_id': ['acct_001', 'acct_002', 'acct_003'],
            'customer_email': ['john@acme.com', 'john@acme.com', 'jane@techcorp.io'],
            'customer_kyc_id': ['kyc_9999', 'kyc_9999', 'kyc_8888'],
            'balance': [5000.00, 2500.50, 12000.00],
            'status': ['active', 'active', 'active'],
            'account_type': ['checking', 'savings', 'checking']
        })

    @pytest.fixture
    def iri_resolver(self):
        """IRI resolver for deterministic customer identification"""
        return IriResolver()

    @pytest.fixture
    def test_ontology_path(self):
        """Get path to test ontology file"""
        test_dir = Path(__file__).parent.parent.parent / 'src' / 'main' / 'python' / 'semantic' / 'tests'
        return str(test_dir / 'shared-ontology-test.ttl')

    @pytest.fixture
    def transformer(self, iri_resolver, test_ontology_path):
        """RDF transformer with test ontology"""
        return SilverToRdfTransformer(iri_resolver, test_ontology_path)

    def test_customer_iri_minting_deterministic(self, iri_resolver, sample_customers_df):
        """Test: Customer IRIs are deterministically minted"""
        row1 = sample_customers_df.iloc[0]
        row2 = sample_customers_df.iloc[0]

        iri1 = iri_resolver.mint_customer_iri(row1['email'], row1['kyc_id'])
        iri2 = iri_resolver.mint_customer_iri(row2['email'], row2['kyc_id'])

        assert iri1 == iri2, "Customer IRIs must be deterministic for deduplication"

    def test_silver_to_rdf_customers_with_types(self, transformer, sample_customers_df):
        """Test: Silver customer data transforms to RDF with rdf:type triples"""
        graph = transformer.transform_customers_to_rdf(sample_customers_df)

        # Query for customers using standard rdf:type
        query = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            SELECT ?customer WHERE {
                ?customer rdf:type fintech:Customer .
            }
        """
        results = list(graph.query(query))

        assert len(results) == 3, f"Expected 3 customers with rdf:type, got {len(results)}"

    def test_silver_to_rdf_accounts_with_types(self, transformer, sample_customers_df, sample_accounts_df):
        """Test: Silver account data transforms to RDF with rdf:type and customer linking"""
        # First transform customers to establish the graph
        transformer.transform_customers_to_rdf(sample_customers_df)
        # Then transform accounts
        accounts_graph = transformer.transform_accounts_to_rdf(sample_accounts_df, sample_customers_df)

        # Query for accounts using standard rdf:type
        query = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            SELECT ?account WHERE {
                ?account rdf:type fintech:Account .
            }
        """
        results = list(accounts_graph.query(query))

        assert len(results) == 3, f"Expected 3 accounts with rdf:type, got {len(results)}"

    def test_customer_account_linking_with_standard_types(self, transformer, sample_customers_df, sample_accounts_df):
        """Test: Accounts are correctly linked to customers via standard RDF"""
        # First transform customers
        transformer.transform_customers_to_rdf(sample_customers_df)
        # Then transform accounts
        accounts_graph = transformer.transform_accounts_to_rdf(sample_accounts_df, sample_customers_df)

        # Query using standard rdf:type and account linking
        query = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            SELECT ?account ?customer WHERE {
                ?account rdf:type fintech:Account ;
                         fintech:accountOwner ?customer .
                ?customer rdf:type fintech:Customer .
            }
        """
        results = list(accounts_graph.query(query))

        assert len(results) >= 3, f"Expected at least 3 account-customer links, got {len(results)}"

    def test_rdf_type_triples_are_queryable(self, transformer, sample_customers_df):
        """Test: rdf:type triples are directly queryable and match W3C RDF spec"""
        from rdflib import Namespace
        graph = transformer.transform_customers_to_rdf(sample_customers_df)
        FINTECH = Namespace("https://chakracommerce.com/ontology/fintech/")

        # Verify rdf:type triples exist at the triple level
        # Filter to only those pointing to fintech:Customer (not ontology definitions)
        rdf_type_triples = [
            (s, p, o) for s, p, o in graph.triples((None, RDF.type, FINTECH.Customer))
        ]

        assert len(rdf_type_triples) >= 3, f"Expected at least 3 rdf:type fintech:Customer triples, got {len(rdf_type_triples)}"
