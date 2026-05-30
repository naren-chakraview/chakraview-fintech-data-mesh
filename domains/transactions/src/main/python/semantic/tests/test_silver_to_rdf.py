"""Unit tests for Transactions domain Silver-to-RDF transformation."""

import pytest
import pandas as pd
import os
from ..silver_to_rdf import SilverToRdfTransformer
from ..iri_resolver import IriResolver
from ..cross_domain_resolver import CrossDomainResolver


class TestSilverToRdfTransformer:
    """Test RDF transformation for transactions and counterparties."""

    @pytest.fixture
    def test_ontology_path(self):
        """Get path to test ontology file in the same directory as this test."""
        test_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(test_dir, "shared-ontology-test.ttl")

    @pytest.fixture
    def resolver(self):
        """Create IRI resolver instance."""
        return IriResolver()

    @pytest.fixture
    def cross_resolver(self):
        """Create cross-domain resolver instance."""
        return CrossDomainResolver()

    @pytest.fixture
    def transformer(self, resolver, cross_resolver, test_ontology_path):
        """Create transformer with test ontology."""
        return SilverToRdfTransformer(resolver, cross_resolver, test_ontology_path)

    @pytest.fixture
    def sample_transactions_df(self):
        """Sample transaction data."""
        return pd.DataFrame({
            'transaction_id': ['txn_001', 'txn_002', 'txn_003'],
            'customer_email': ['john@acme.com', 'jane@acme.com', 'bob@widgets.com'],
            'customer_kyc_id': ['kyc_9999', 'kyc_8888', 'kyc_7777'],
            'counterparty_id': ['stripe', 'paypal', 'square'],
            'amount': [2500.00, 1500.00, 500.00],
            'status': ['failed', 'executed', 'executed'],
            'transaction_date': ['2026-05-24T08:00:00Z', '2026-05-22T14:30:00Z', '2026-05-20T10:15:00Z']
        })

    @pytest.fixture
    def sample_counterparties_df(self):
        """Sample counterparty data."""
        return pd.DataFrame({
            'counterparty_id': ['stripe', 'paypal', 'square'],
            'name': ['Stripe', 'PayPal', 'Square'],
            'type': ['processor', 'processor', 'processor']
        })

    def test_transform_transactions(self, transformer, sample_transactions_df):
        """Test: Silver transaction data transforms to RDF triples."""
        graph = transformer.transform_transactions_to_rdf(sample_transactions_df)

        # Verify triples were generated (at least 7 per transaction)
        assert len(graph) >= 21, f"Expected >= 21 triples for 3 transactions, got {len(graph)}"

    def test_transform_counterparties(self, transformer, sample_counterparties_df):
        """Test: Silver counterparty data transforms to RDF triples."""
        graph = transformer.transform_counterparties_to_rdf(sample_counterparties_df)

        # Verify triples were generated (at least 4 per counterparty)
        assert len(graph) >= 12, f"Expected >= 12 triples for 3 counterparties, got {len(graph)}"

    def test_transaction_iri_format_in_rdf(self, transformer, sample_transactions_df):
        """Test: Transaction IRIs in RDF have correct format."""
        graph = transformer.transform_transactions_to_rdf(sample_transactions_df)

        # Query for transaction IRIs
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT ?transaction WHERE {
                ?transaction rdf:type fintech:Transaction .
            }
        """
        results = list(graph.query(query))

        assert len(results) == 3, f"Expected 3 transactions, got {len(results)}"

    def test_counterparty_iri_format_in_rdf(self, transformer, sample_counterparties_df):
        """Test: Counterparty IRIs in RDF have correct format."""
        graph = transformer.transform_counterparties_to_rdf(sample_counterparties_df)

        # Query for counterparty IRIs
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT ?counterparty WHERE {
                ?counterparty rdf:type fintech:Counterparty .
            }
        """
        results = list(graph.query(query))

        assert len(results) == 3, f"Expected 3 counterparties, got {len(results)}"

    def test_transaction_customer_linking(self, transformer, sample_transactions_df):
        """Test: Transactions are linked to customer IRIs."""
        graph = transformer.transform_transactions_to_rdf(sample_transactions_df)

        # Query for transaction-customer links
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT ?transaction ?customer WHERE {
                ?transaction rdf:type fintech:Transaction ;
                             fintech:transactionDebtor ?customer .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 3, f"Expected >= 3 transaction-customer links, got {len(results)}"

    def test_transaction_counterparty_linking(self, transformer, sample_transactions_df):
        """Test: Transactions are linked to counterparty IRIs."""
        graph = transformer.transform_transactions_to_rdf(sample_transactions_df)

        # Query for transaction-counterparty links
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?transaction ?counterparty WHERE {
                ?transaction fintech:transactionCreditor ?counterparty .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 3, f"Expected >= 3 transaction-counterparty links, got {len(results)}"

    def test_rdf_type_declarations(self, transformer, sample_transactions_df):
        """Test: All entities have proper rdf:type declarations."""
        graph = transformer.transform_transactions_to_rdf(sample_transactions_df)

        # Count type triples
        query = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT (COUNT(?type) as ?count) WHERE {
                ?s rdf:type ?type .
            }
        """
        results = list(graph.query(query))
        count = int(results[0][0])

        assert count >= 3, f"Expected >= 3 rdf:type declarations (one per transaction), got {count}"

    def test_metadata_tagging_transactions(self, transformer, sample_transactions_df):
        """Test: Transaction RDF triples include source metadata."""
        graph = transformer.transform_transactions_to_rdf(sample_transactions_df)

        # Query for sourceSystem metadata
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?system WHERE {
                ?transaction fintech:sourceSystem ?system .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 1, "Expected sourceSystem metadata on transactions"
        assert str(results[0][0]) == "transactions", "sourceSystem should be 'transactions'"

    def test_metadata_tagging_counterparties(self, transformer, sample_counterparties_df):
        """Test: Counterparty RDF triples include source metadata."""
        graph = transformer.transform_counterparties_to_rdf(sample_counterparties_df)

        # Query for sourceSystem metadata
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?system WHERE {
                ?counterparty fintech:sourceSystem ?system .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 1, "Expected sourceSystem metadata on counterparties"
        assert str(results[0][0]) == "transactions", "sourceSystem should be 'transactions'"

    def test_transaction_properties_present(self, transformer, sample_transactions_df):
        """Test: Transaction properties are correctly populated."""
        graph = transformer.transform_transactions_to_rdf(sample_transactions_df)

        # Query for transaction properties
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?id ?amount ?status WHERE {
                ?transaction fintech:transactionId ?id ;
                             fintech:transactionAmount ?amount ;
                             fintech:transactionStatus ?status .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 3, "Expected all transaction properties to be present"

    def test_counterparty_properties_present(self, transformer, sample_counterparties_df):
        """Test: Counterparty properties are correctly populated."""
        graph = transformer.transform_counterparties_to_rdf(sample_counterparties_df)

        # Query for counterparty properties
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?id ?name ?type WHERE {
                ?counterparty fintech:counterpartyId ?id ;
                              fintech:counterpartyName ?name ;
                              fintech:counterpartyType ?type .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 3, "Expected all counterparty properties to be present"

    def test_get_graph(self, transformer, sample_transactions_df):
        """Test: Retrieving the RDF graph after transformation."""
        transformer.transform_transactions_to_rdf(sample_transactions_df)
        graph = transformer.get_graph()

        assert graph is not None, "Graph should not be None"
        assert len(graph) > 0, "Graph should contain triples"

    def test_multiple_transformations_accumulate(self, transformer, sample_transactions_df, sample_counterparties_df):
        """Test: Multiple transformations accumulate triples in same graph."""
        transformer.transform_transactions_to_rdf(sample_transactions_df)
        transformer.transform_counterparties_to_rdf(sample_counterparties_df)
        graph = transformer.get_graph()

        # Should have triples from both transformations
        assert len(graph) >= 30, f"Expected >= 30 total triples, got {len(graph)}"
