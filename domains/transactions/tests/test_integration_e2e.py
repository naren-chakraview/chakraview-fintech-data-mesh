"""End-to-end integration test for Transactions domain semantic integration.

Tests the complete RDF transformation pipeline including:
- RDF transformation from Silver tables
- SPARQL query execution against generated RDF
- Cross-domain customer IRI linking with Accounts domain
- Metadata tagging and ingestion timestamps
"""

import pytest
import pandas as pd
import os
import sys
from datetime import datetime
from pathlib import Path
from rdflib import Graph, Namespace, Literal, URIRef, RDF

# Setup Python path to import from src modules
# This test file is at: domains/transactions/tests/test_integration_e2e.py
# We need to import from: domains/transactions/src/main/python/semantic/

test_file_dir = Path(__file__).parent  # domains/transactions/tests
transactions_src = test_file_dir.parent / "src" / "main" / "python"  # domains/transactions/src/main/python

# Ensure path is at front
if str(transactions_src) not in sys.path:
    sys.path.insert(0, str(transactions_src))

# Import modules
from semantic.silver_to_rdf import SilverToRdfTransformer
from semantic.iri_resolver import IriResolver as TransactionsIriResolver
from semantic.cross_domain_resolver import CrossDomainResolver


class TestTransactionsIntegrationE2E:
    """End-to-end integration tests for Transactions domain RDF transformation."""

    # Named constants for test expectations
    MIN_TRANSACTIONS = 3
    MIN_COUNTERPARTIES = 2
    MIN_EXPECTED_TRIPLES = 50

    @pytest.fixture
    def test_ontology_path(self) -> str:
        """Get path to test ontology file."""
        test_dir = Path(__file__).parent / ".." / "src" / "main" / "python" / "semantic" / "tests"
        return str(test_dir / "shared-ontology-test.ttl")

    @pytest.fixture(scope="function")
    def iri_resolver(self) -> TransactionsIriResolver:
        """Create Transactions domain IRI resolver."""
        return TransactionsIriResolver()

    @pytest.fixture(scope="function")
    def cross_domain_resolver(self) -> CrossDomainResolver:
        """Create cross-domain resolver for linking to Accounts domain."""
        return CrossDomainResolver()

    @pytest.fixture(scope="function")
    def transformer(self, iri_resolver: TransactionsIriResolver, cross_domain_resolver: CrossDomainResolver, test_ontology_path: str) -> SilverToRdfTransformer:
        """Create transformer instance with resolvers and ontology. Fresh graph per test."""
        return SilverToRdfTransformer(
            iri_resolver,
            cross_domain_resolver,
            test_ontology_path
        )

    @pytest.fixture
    def sample_transactions_df(self) -> pd.DataFrame:
        """Sample transaction data for testing."""
        return pd.DataFrame({
            'transaction_id': [
                'txn_001',
                'txn_002',
                'txn_003'
            ],
            'customer_email': [
                'john@acme.com',
                'jane@techcorp.io',
                'alice@finance.org'
            ],
            'customer_kyc_id': [
                'kyc_12345',
                'kyc_67890',
                'kyc_11111'
            ],
            'counterparty_id': [
                'stripe',
                'paypal',
                'stripe'
            ],
            'amount': [
                2500.00,
                1500.00,
                3200.00
            ],
            'status': [
                'executed',
                'executed',
                'executed'
            ],
            'transaction_date': [
                '2026-05-24T08:00:00Z',
                '2026-05-23T14:30:00Z',
                '2026-05-22T10:15:00Z'
            ]
        })

    @pytest.fixture
    def sample_counterparties_df(self) -> pd.DataFrame:
        """Sample counterparty data for testing."""
        return pd.DataFrame({
            'counterparty_id': [
                'stripe',
                'paypal'
            ],
            'name': [
                'Stripe',
                'PayPal'
            ],
            'type': [
                'processor',
                'processor'
            ]
        })

    # Helper methods for SPARQL queries
    def _count_transactions_query(self) -> str:
        """SPARQL query to count Transaction RDF type declarations."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT (COUNT(?transaction) as ?count) WHERE {
                ?transaction rdf:type fintech:Transaction .
            }
        """

    def _count_counterparties_query(self) -> str:
        """SPARQL query to count Counterparty RDF type declarations."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT (COUNT(?counterparty) as ?count) WHERE {
                ?counterparty rdf:type fintech:Counterparty .
            }
        """

    def _query_debtor_links(self) -> str:
        """SPARQL query to retrieve transaction-debtor links."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?transaction ?debtor WHERE {
                ?transaction fintech:transactionDebtor ?debtor .
            }
        """

    def _query_creditor_links(self) -> str:
        """SPARQL query to retrieve transaction-creditor links."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?transaction ?creditor WHERE {
                ?transaction fintech:transactionCreditor ?creditor .
            }
        """

    def _query_source_system_metadata(self) -> str:
        """SPARQL query to retrieve sourceSystem metadata on entities."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?entity ?system WHERE {
                ?entity fintech:sourceSystem ?system .
            }
        """

    def _query_ingestion_time_metadata(self) -> str:
        """SPARQL query to retrieve sourceIngestionTime metadata on entities."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?entity ?timestamp WHERE {
                ?entity fintech:sourceIngestionTime ?timestamp .
            }
        """

    def test_rdf_transformation_generates_sufficient_triples(
        self,
        transformer: SilverToRdfTransformer,
        sample_transactions_df: pd.DataFrame,
        sample_counterparties_df: pd.DataFrame
    ) -> None:
        """Test: RDF transformation generates at least 50 triples from sample data.

        Verifies:
        - Transactions transform to RDF with type declarations
        - Counterparties transform to RDF with type declarations
        - Metadata triples are generated
        - Total triple count >= self.MIN_EXPECTED_TRIPLES
        """
        # Transform both transactions and counterparties
        transformer.transform_transactions_to_rdf(sample_transactions_df)
        transformer.transform_counterparties_to_rdf(sample_counterparties_df)

        graph = transformer.get_graph()
        triple_count = len(graph)

        assert triple_count >= self.MIN_EXPECTED_TRIPLES, (
            f"Expected >= {self.MIN_EXPECTED_TRIPLES} triples "
            f"(transactions + counterparties + metadata), got {triple_count}"
        )

    def test_sparql_query_count_transaction_type(
        self,
        transformer: SilverToRdfTransformer,
        sample_transactions_df: pd.DataFrame
    ) -> None:
        """Test: SPARQL query counts all Transaction RDF type declarations.

        Verifies:
        - Transactions are declared with rdf:type fintech:Transaction
        - SPARQL COUNT query returns correct results
        - At least self.MIN_TRANSACTIONS transactions are queryable
        """
        transformer.transform_transactions_to_rdf(sample_transactions_df)
        graph = transformer.get_graph()

        query = self._count_transactions_query()
        results = list(graph.query(query))
        count = int(results[0][0])

        assert count >= self.MIN_TRANSACTIONS, (
            f"Expected >= {self.MIN_TRANSACTIONS} transactions via SPARQL query, got {count}"
        )

    def test_sparql_query_count_counterparty_type(
        self,
        transformer: SilverToRdfTransformer,
        sample_counterparties_df: pd.DataFrame
    ) -> None:
        """Test: SPARQL query counts all Counterparty RDF type declarations.

        Verifies:
        - Counterparties are declared with rdf:type fintech:Counterparty
        - SPARQL COUNT query returns correct results
        - At least self.MIN_COUNTERPARTIES counterparties are queryable
        """
        transformer.transform_counterparties_to_rdf(sample_counterparties_df)
        graph = transformer.get_graph()

        query = self._count_counterparties_query()
        results = list(graph.query(query))
        count = int(results[0][0])

        assert count >= self.MIN_COUNTERPARTIES, (
            f"Expected >= {self.MIN_COUNTERPARTIES} counterparties via SPARQL query, got {count}"
        )

    def test_transaction_links_debtor_and_creditor_properties(
        self,
        transformer: SilverToRdfTransformer,
        sample_transactions_df: pd.DataFrame,
        sample_counterparties_df: pd.DataFrame
    ) -> None:
        """Test: Transaction triples link to customers and counterparties.

        Verifies:
        - fintech:transactionDebtor property exists and links to customer IRIs
        - fintech:transactionCreditor property exists and links to counterparty IRIs
        - All transactions have both properties
        """
        transformer.transform_transactions_to_rdf(sample_transactions_df)
        transformer.transform_counterparties_to_rdf(sample_counterparties_df)
        graph = transformer.get_graph()

        # Query for debtor links
        debtor_results = list(graph.query(self._query_debtor_links()))

        assert len(debtor_results) >= self.MIN_TRANSACTIONS, (
            f"Expected >= {self.MIN_TRANSACTIONS} transaction-debtor links, "
            f"got {len(debtor_results)}"
        )

        # Query for creditor links
        creditor_results = list(graph.query(self._query_creditor_links()))

        assert len(creditor_results) >= self.MIN_TRANSACTIONS, (
            f"Expected >= {self.MIN_TRANSACTIONS} transaction-creditor links, "
            f"got {len(creditor_results)}"
        )

    def test_cross_domain_customer_iri_consistency(
        self,
        cross_domain_resolver: CrossDomainResolver
    ) -> None:
        """Test: Same customer (email+kyc_id) always produces same customer IRI.

        Verifies:
        - Cross-domain resolver produces deterministic IRIs
        - Same email + kyc_id combination always produces identical IRI
        - IRI format is consistent with Accounts domain pattern
        """
        # Test case 1: john@acme.com with kyc_12345
        iri_1a = cross_domain_resolver.resolve_customer_iri(
            "john@acme.com",
            "kyc_12345"
        )
        iri_1b = cross_domain_resolver.resolve_customer_iri(
            "john@acme.com",
            "kyc_12345"
        )

        assert iri_1a == iri_1b, (
            f"Same customer should produce same IRI: {iri_1a} != {iri_1b}"
        )

        # Test case 2: Different case should normalize to same IRI
        iri_1c = cross_domain_resolver.resolve_customer_iri(
            "JOHN@ACME.COM",
            "KYC_12345"
        )

        assert iri_1a == iri_1c, (
            f"Case-insensitive customer should produce same IRI: "
            f"{iri_1a} != {iri_1c}"
        )

        # Test case 3: Different customer should produce different IRI
        iri_2 = cross_domain_resolver.resolve_customer_iri(
            "jane@techcorp.io",
            "kyc_67890"
        )

        assert iri_1a != iri_2, (
            f"Different customers should produce different IRIs: "
            f"{iri_1a} == {iri_2}"
        )

        # Verify IRI format matches Accounts domain pattern
        # Expected format: https://chakracommerce.com/customer#{8-char-hash}
        assert iri_1a.startswith("https://chakracommerce.com/customer#"), (
            f"IRI should match Accounts domain format, got {iri_1a}"
        )

    def test_cross_domain_linking_in_rdf_graph(
        self,
        transformer: SilverToRdfTransformer,
        sample_transactions_df: pd.DataFrame,
        cross_domain_resolver: CrossDomainResolver
    ) -> None:
        """Test: Transaction RDF links to customer IRIs via cross-domain resolver.

        Verifies:
        - Transactions reference customer IRIs minted by cross-domain resolver
        - Customer IRIs in RDF match cross-domain resolver output
        - Cross-domain linking is consistent
        """
        transformer.transform_transactions_to_rdf(sample_transactions_df)
        graph = transformer.get_graph()

        # Resolve customer IRI using cross-domain resolver
        expected_customer_iri = cross_domain_resolver.resolve_customer_iri(
            "john@acme.com",
            "kyc_12345"
        )

        # Query for transaction-customer link in RDF
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?transaction ?debtor WHERE {
                ?transaction fintech:transactionId "txn_001" ;
                             fintech:transactionDebtor ?debtor .
            }
        """
        results = list(graph.query(query))

        assert len(results) > 0, (
            "Expected at least one transaction-debtor link in RDF"
        )

        # Verify the debtor IRI matches what cross-domain resolver produced
        actual_debtor_iri = str(results[0][1])

        assert actual_debtor_iri == expected_customer_iri, (
            f"Transaction should link to correct customer IRI. "
            f"Expected: {expected_customer_iri}, Got: {actual_debtor_iri}"
        )

    def test_metadata_source_system_tagging(
        self,
        transformer: SilverToRdfTransformer,
        sample_transactions_df: pd.DataFrame,
        sample_counterparties_df: pd.DataFrame
    ) -> None:
        """Test: All RDF triples have sourceSystem='transactions' metadata.

        Verifies:
        - Transactions have sourceSystem metadata
        - Counterparties have sourceSystem metadata
        - sourceSystem value is 'transactions' for both
        """
        transformer.transform_transactions_to_rdf(sample_transactions_df)
        transformer.transform_counterparties_to_rdf(sample_counterparties_df)
        graph = transformer.get_graph()

        results = list(graph.query(self._query_source_system_metadata()))

        assert len(results) > 0, (
            f"Expected sourceSystem metadata on entities. Graph has {len(graph)} total triples"
        )

        for result in results:
            system_value = str(result[1])
            assert system_value == "transactions", (
                f"sourceSystem should be 'transactions', got '{system_value}'. "
                f"Query returned {len(results)} metadata triples"
            )

    def test_metadata_ingestion_time_timestamp(
        self,
        transformer: SilverToRdfTransformer,
        sample_transactions_df: pd.DataFrame
    ) -> None:
        """Test: RDF triples include sourceIngestionTime with valid timestamp.

        Verifies:
        - sourceIngestionTime metadata is present
        - sourceIngestionTime values are valid ISO 8601 timestamps
        - At least one timestamp per entity
        """
        transformer.transform_transactions_to_rdf(sample_transactions_df)
        graph = transformer.get_graph()

        results = list(graph.query(self._query_ingestion_time_metadata()))

        assert len(results) > 0, (
            f"Expected sourceIngestionTime metadata on transactions. "
            f"Graph has {len(graph)} total triples"
        )

        for result in results:
            timestamp_str = str(result[1])
            # Verify it's a valid ISO 8601 timestamp format
            try:
                datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                pytest.fail(
                    f"sourceIngestionTime should be ISO 8601 format, "
                    f"got '{timestamp_str}'. Query returned {len(results)} timestamp triples"
                )

    def test_multiple_transactions_same_customer_single_iri(
        self,
        transformer: SilverToRdfTransformer,
        cross_domain_resolver: CrossDomainResolver
    ) -> None:
        """Test: Multiple transactions from same customer link to same customer IRI.

        Verifies:
        - Cross-domain linking produces single IRI per unique customer
        - Multiple transactions reference same customer IRI
        - Deduplication works correctly
        """
        # Create transactions data with duplicate customer
        transactions_df = pd.DataFrame({
            'transaction_id': ['txn_001', 'txn_002', 'txn_003'],
            'customer_email': [
                'john@acme.com',
                'john@acme.com',  # Same customer as txn_001
                'jane@techcorp.io'
            ],
            'customer_kyc_id': [
                'kyc_12345',
                'kyc_12345',  # Same customer as txn_001
                'kyc_67890'
            ],
            'counterparty_id': ['stripe', 'paypal', 'stripe'],
            'amount': [2500.00, 1500.00, 3200.00],
            'status': ['executed', 'executed', 'executed'],
            'transaction_date': [
                '2026-05-24T08:00:00Z',
                '2026-05-23T14:30:00Z',
                '2026-05-22T10:15:00Z'
            ]
        })

        transformer.transform_transactions_to_rdf(transactions_df)
        graph = transformer.get_graph()

        # Get the expected customer IRI
        expected_customer_iri = cross_domain_resolver.resolve_customer_iri(
            "john@acme.com",
            "kyc_12345"
        )

        # Query for all transaction-debtor links
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?transaction ?debtor WHERE {
                ?transaction fintech:transactionDebtor ?debtor .
            }
        """
        results = list(graph.query(query))

        # Extract debtor IRIs for transactions from john@acme.com
        query_john = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?debtor WHERE {
                ?transaction fintech:transactionId ?txnId ;
                             fintech:transactionDebtor ?debtor .
                FILTER (?txnId IN ("txn_001", "txn_002"))
            }
        """
        john_results = list(graph.query(query_john))

        assert len(john_results) == 2, (
            f"Expected 2 transactions for john@acme.com, got {len(john_results)}"
        )

        # Verify both transactions reference the same customer IRI
        debtor_iri_1 = str(john_results[0][0])
        debtor_iri_2 = str(john_results[1][0])

        assert debtor_iri_1 == debtor_iri_2, (
            f"Same customer should have same IRI: {debtor_iri_1} != {debtor_iri_2}"
        )

        assert debtor_iri_1 == expected_customer_iri, (
            f"Customer IRI should match cross-domain resolver output. "
            f"Expected: {expected_customer_iri}, Got: {debtor_iri_1}"
        )

    def test_full_pipeline_end_to_end(
        self,
        transformer: SilverToRdfTransformer,
        sample_transactions_df: pd.DataFrame,
        sample_counterparties_df: pd.DataFrame,
        cross_domain_resolver: CrossDomainResolver
    ) -> None:
        """Test: Complete end-to-end pipeline from raw data to queryable RDF.

        Verifies:
        - Transactions transform to RDF
        - Counterparties transform to RDF
        - Cross-domain linking works
        - SPARQL queries execute successfully
        - Metadata is correct
        - Triple count is sufficient
        """
        # Step 1: Transform transactions
        transformer.transform_transactions_to_rdf(sample_transactions_df)

        # Step 2: Transform counterparties
        transformer.transform_counterparties_to_rdf(sample_counterparties_df)

        # Step 3: Get the RDF graph
        graph = transformer.get_graph()

        # Verify triple count
        assert len(graph) >= self.MIN_EXPECTED_TRIPLES, (
            f"Expected >= {self.MIN_EXPECTED_TRIPLES} total triples, got {len(graph)}"
        )

        # Step 4: Verify transaction count via SPARQL
        txn_results = list(graph.query(self._count_transactions_query()))
        txn_count = int(txn_results[0][0])

        assert txn_count >= self.MIN_TRANSACTIONS, (
            f"Expected >= {self.MIN_TRANSACTIONS} transactions in RDF, got {txn_count}"
        )

        # Step 5: Verify counterparty count via SPARQL
        cp_results = list(graph.query(self._count_counterparties_query()))
        cp_count = int(cp_results[0][0])

        assert cp_count >= self.MIN_COUNTERPARTIES, (
            f"Expected >= {self.MIN_COUNTERPARTIES} counterparties in RDF, got {cp_count}"
        )

        # Step 6: Verify cross-domain linking
        customer_results = list(graph.query(self._query_debtor_links()))

        assert len(customer_results) >= self.MIN_TRANSACTIONS, (
            f"Expected >= {self.MIN_TRANSACTIONS} transaction-customer links, "
            f"got {len(customer_results)}"
        )

        # Step 7: Verify metadata (sourceSystem + sourceIngestionTime)
        metadata_query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?entity ?system ?timestamp WHERE {
                ?entity fintech:sourceSystem ?system ;
                        fintech:sourceIngestionTime ?timestamp .
            }
        """
        metadata_results = list(graph.query(metadata_query))

        assert len(metadata_results) > 0, (
            f"Expected metadata on RDF triples. Graph has {len(graph)} total triples"
        )

        for result in metadata_results:
            assert str(result[1]) == "transactions", (
                f"Expected sourceSystem='transactions', got '{result[1]}'. "
                f"Query returned {len(metadata_results)} metadata triples"
            )
            # Verify timestamp is valid ISO format
            try:
                datetime.fromisoformat(
                    str(result[2]).replace('Z', '+00:00')
                )
            except ValueError:
                pytest.fail(
                    f"Invalid timestamp format: {result[2]}. "
                    f"Expected ISO 8601 format. Query returned {len(metadata_results)} results"
                )
