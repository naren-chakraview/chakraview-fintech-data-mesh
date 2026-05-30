import pytest
import pandas as pd
import os
from ..silver_to_rdf import SilverToRdfTransformer
from ..iri_resolver import IriResolver


class TestSilverToRdfTransformer:

    @pytest.fixture
    def test_ontology_path(self):
        """Get path to test ontology file in the same directory as this test"""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(test_dir, "shared-ontology-test.ttl")

    @pytest.fixture
    def resolver(self):
        return IriResolver()

    @pytest.fixture
    def transformer(self, resolver, test_ontology_path):
        """Create transformer with test ontology"""
        return SilverToRdfTransformer(resolver, test_ontology_path)

    def test_transform_customers(self, transformer):
        """Test transformation of customer Silver table to RDF"""
        customers_df = pd.DataFrame({
            'email': ['john@acme.com'],
            'kyc_id': ['kyc_123'],
            'name': ['John Doe'],
            'status': ['active']
        })

        graph = transformer.transform_customers_to_rdf(customers_df)

        # Verify triple was added
        assert len(graph) > 0
        # Graph should contain at least the customer properties
        assert len(list(graph.triples((None, None, None)))) > 0

    def test_transform_customers_multiple_records(self, transformer):
        """Test transformation of multiple customer records"""
        customers_df = pd.DataFrame({
            'email': ['john@acme.com', 'jane@acme.com'],
            'kyc_id': ['kyc_123', 'kyc_456'],
            'name': ['John Doe', 'Jane Smith'],
            'status': ['active', 'active']
        })

        graph = transformer.transform_customers_to_rdf(customers_df)

        # Each customer should generate multiple triples (name, email, status, source, time)
        assert len(graph) >= 10  # At least 5 properties * 2 customers

    def test_transform_accounts(self, transformer):
        """Test transformation of account Silver table to RDF"""
        customers_df = pd.DataFrame({
            'email': ['john@acme.com'],
            'kyc_id': ['kyc_123'],
            'name': ['John Doe'],
            'status': ['active']
        })

        accounts_df = pd.DataFrame({
            'account_id': ['acct_001'],
            'customer_email': ['john@acme.com'],
            'customer_kyc_id': ['kyc_123'],
            'balance': [1000.50],
            'status': ['active'],
            'account_type': ['checking']
        })

        # First transform customers to populate the graph
        transformer.transform_customers_to_rdf(customers_df)
        # Then transform accounts
        graph = transformer.transform_accounts_to_rdf(accounts_df, customers_df)

        # Verify triples were added
        assert len(graph) > 0

    def test_transform_accounts_multiple_records(self, transformer):
        """Test transformation of multiple account records"""
        customers_df = pd.DataFrame({
            'email': ['john@acme.com', 'jane@acme.com'],
            'kyc_id': ['kyc_123', 'kyc_456'],
            'name': ['John Doe', 'Jane Smith'],
            'status': ['active', 'active']
        })

        accounts_df = pd.DataFrame({
            'account_id': ['acct_001', 'acct_002'],
            'customer_email': ['john@acme.com', 'jane@acme.com'],
            'customer_kyc_id': ['kyc_123', 'kyc_456'],
            'balance': [1000.50, 2500.75],
            'status': ['active', 'active'],
            'account_type': ['checking', 'savings']
        })

        # First transform customers
        transformer.transform_customers_to_rdf(customers_df)
        # Then transform accounts
        graph = transformer.transform_accounts_to_rdf(accounts_df, customers_df)

        # Each account should generate multiple triples (id, balance, status, type, owner, source, time)
        assert len(graph) >= 20  # At least 7 properties * 2 accounts + customer triples

    def test_get_graph(self, transformer):
        """Test retrieving the RDF graph"""
        customers_df = pd.DataFrame({
            'email': ['john@acme.com'],
            'kyc_id': ['kyc_123'],
            'name': ['John Doe'],
            'status': ['active']
        })

        transformer.transform_customers_to_rdf(customers_df)
        graph = transformer.get_graph()

        assert graph is not None
        assert len(graph) > 0
