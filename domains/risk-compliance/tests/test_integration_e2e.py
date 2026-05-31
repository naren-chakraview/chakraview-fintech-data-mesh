"""End-to-end integration test for Risk/Compliance domain semantic integration.

Tests the complete RDF transformation pipeline including:
- RDF transformation from Silver tables
- SPARQL query execution against generated RDF
- Cross-domain customer IRI linking with Accounts domain
- Metadata tagging and ingestion timestamps
- Enum validation for risk levels, KYC status, compliance status
"""

import pytest
import pandas as pd
import os
import sys
from datetime import datetime
from pathlib import Path
from rdflib import Graph, Namespace, Literal, URIRef, RDF

# Setup Python path to import from src modules
# This test file is at: domains/risk-compliance/tests/test_integration_e2e.py
# We need to import from: domains/risk-compliance/src/main/python/semantic/

test_file_dir = Path(__file__).parent  # domains/risk-compliance/tests
risk_compliance_src = test_file_dir.parent / "src" / "main" / "python"  # domains/risk-compliance/src/main/python

# Ensure path is at front
if str(risk_compliance_src) not in sys.path:
    sys.path.insert(0, str(risk_compliance_src))

# Import modules
from semantic.silver_to_rdf import SilverToRdfTransformer
from semantic.iri_resolver import IriResolver as RiskComplianceIriResolver
from semantic.cross_domain_resolver import CrossDomainResolver


class TestRiskComplianceIntegrationE2E:
    """End-to-end integration tests for Risk/Compliance domain RDF transformation."""

    # Named constants for test expectations
    MIN_RISK_PROFILES = 5
    MIN_EXPECTED_TRIPLES = 50

    @pytest.fixture
    def test_ontology_path(self) -> str:
        """Get path to test ontology file."""
        test_dir = Path(__file__).parent / ".." / "src" / "main" / "python" / "semantic" / "tests"
        return str(test_dir / "shared-ontology-test.ttl")

    @pytest.fixture(scope="function")
    def iri_resolver(self) -> RiskComplianceIriResolver:
        """Create Risk/Compliance domain IRI resolver."""
        return RiskComplianceIriResolver()

    @pytest.fixture(scope="function")
    def cross_domain_resolver(self) -> CrossDomainResolver:
        """Create cross-domain resolver for linking to Accounts domain."""
        return CrossDomainResolver()

    @pytest.fixture(scope="function")
    def transformer(self, iri_resolver: RiskComplianceIriResolver, cross_domain_resolver: CrossDomainResolver, test_ontology_path: str) -> SilverToRdfTransformer:
        """Create transformer instance with resolvers and ontology. Fresh graph per test."""
        return SilverToRdfTransformer(
            iri_resolver,
            cross_domain_resolver,
            test_ontology_path
        )

    @pytest.fixture
    def sample_risk_profiles_df(self) -> pd.DataFrame:
        """Sample risk profile data for testing."""
        return pd.DataFrame({
            'risk_id': [
                'risk_001',
                'risk_002',
                'risk_003',
                'risk_004',
                'risk_005',
                'risk_006'
            ],
            'customer_email': [
                'john@acme.com',
                'jane@techcorp.io',
                'alice@finance.org',
                'bob@startup.com',
                'charlie@banking.co.uk',
                'diana@corp.net'
            ],
            'customer_kyc_id': [
                'kyc_12345',
                'kyc_67890',
                'kyc_11111',
                'kyc_22222',
                'kyc_33333',
                'kyc_44444'
            ],
            'risk_score': [
                0.92,
                0.45,
                0.78,
                0.15,
                0.88,
                0.55
            ],
            'risk_level': [
                'HIGH',
                'LOW',
                'MEDIUM',
                'LOW',
                'CRITICAL',
                'MEDIUM'
            ],
            'compliance_status': [
                'UNDER_REVIEW',
                'COMPLIANT',
                'NON_COMPLIANT',
                'COMPLIANT',
                'SUSPENDED',
                'UNDER_REVIEW'
            ],
            'kyc_status': [
                'VERIFIED',
                'VERIFIED',
                'IN_PROGRESS',
                'VERIFIED',
                'REJECTED',
                'VERIFIED'
            ],
            'fraud_flags_count': [
                2,
                0,
                1,
                0,
                5,
                1
            ],
            'last_review_date': [
                datetime(2026, 5, 20, 14, 30, 0),
                datetime(2026, 5, 18, 10, 15, 0),
                datetime(2026, 5, 19, 16, 45, 0),
                datetime(2026, 5, 21, 11, 0, 0),
                datetime(2026, 5, 17, 9, 30, 0),
                datetime(2026, 5, 20, 13, 20, 0)
            ],
            'next_review_date': [
                datetime(2026, 6, 20, 14, 30, 0),
                datetime(2026, 6, 18, 10, 15, 0),
                datetime(2026, 6, 19, 16, 45, 0),
                datetime(2026, 6, 21, 11, 0, 0),
                datetime(2026, 6, 17, 9, 30, 0),
                datetime(2026, 6, 20, 13, 20, 0)
            ],
            'review_notes': [
                'High transaction volume flagged',
                'Routine review completed',
                'Fraud investigation ongoing',
                'Low risk customer',
                'Account suspended pending review',
                'Multiple flagged transactions'
            ]
        })

    # Helper methods for SPARQL queries
    def _count_risk_profiles_query(self) -> str:
        """SPARQL query to count RiskProfile RDF type declarations."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT (COUNT(?rp) as ?count) WHERE {
                ?rp rdf:type fintech:RiskProfile .
            }
        """

    def _query_high_risk_profiles(self) -> str:
        """SPARQL query to retrieve HIGH and CRITICAL risk profiles."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?rp ?riskLevel WHERE {
                ?rp fintech:riskLevel ?riskLevel .
                FILTER (?riskLevel IN ("HIGH", "CRITICAL"))
            }
        """

    def _query_non_compliant_customers(self) -> str:
        """SPARQL query to retrieve NON_COMPLIANT and SUSPENDED risk profiles."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?rp ?status WHERE {
                ?rp fintech:complianceStatus ?status .
                FILTER (?status IN ("NON_COMPLIANT", "SUSPENDED"))
            }
        """

    def _query_customer_links(self) -> str:
        """SPARQL query to retrieve risk profile-customer links."""
        return """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?rp ?customer WHERE {
                ?rp fintech:forCustomer ?customer .
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
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: RDF transformation generates at least 50 triples from sample data.

        Verifies:
        - Risk profiles transform to RDF with type declarations
        - Metadata triples are generated
        - Total triple count >= self.MIN_EXPECTED_TRIPLES
        """
        # Transform risk profiles
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        graph = transformer.get_graph()
        triple_count = len(graph)

        assert triple_count >= self.MIN_EXPECTED_TRIPLES, (
            f"Expected >= {self.MIN_EXPECTED_TRIPLES} triples "
            f"(risk profiles + metadata), got {triple_count}"
        )

    def test_sparql_query_risk_profiles_type(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: SPARQL query counts all RiskProfile RDF type declarations.

        Verifies:
        - Risk profiles are declared with rdf:type fintech:RiskProfile
        - SPARQL COUNT query returns correct results
        - At least self.MIN_RISK_PROFILES risk profiles are queryable
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        query = self._count_risk_profiles_query()
        results = list(graph.query(query))
        count = int(results[0][0])

        assert count >= self.MIN_RISK_PROFILES, (
            f"Expected >= {self.MIN_RISK_PROFILES} risk profiles via SPARQL query, got {count}"
        )

    def test_sparql_query_high_risk_profiles(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: SPARQL query identifies HIGH and CRITICAL risk profiles.

        Verifies:
        - HIGH and CRITICAL risk profiles are queryable via SPARQL
        - Results include correct risk level values
        - At least one HIGH or CRITICAL risk profile exists
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        query = self._query_high_risk_profiles()
        results = list(graph.query(query))

        assert len(results) >= 1, (
            f"Expected >= 1 HIGH/CRITICAL risk profile via SPARQL query, got {len(results)}"
        )

        # Verify all results have correct risk levels
        for result in results:
            risk_level = str(result[1])
            assert risk_level in ["HIGH", "CRITICAL"], (
                f"Risk level should be HIGH or CRITICAL, got {risk_level}"
            )

    def test_sparql_query_non_compliant_customers(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: SPARQL query identifies NON_COMPLIANT and SUSPENDED profiles.

        Verifies:
        - NON_COMPLIANT and SUSPENDED profiles are queryable via SPARQL
        - Results include correct compliance status values
        - At least one non-compliant profile exists
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        query = self._query_non_compliant_customers()
        results = list(graph.query(query))

        assert len(results) >= 1, (
            f"Expected >= 1 NON_COMPLIANT/SUSPENDED profile via SPARQL query, got {len(results)}"
        )

        # Verify all results have correct compliance status values
        for result in results:
            status = str(result[1])
            assert status in ["NON_COMPLIANT", "SUSPENDED"], (
                f"Compliance status should be NON_COMPLIANT or SUSPENDED, got {status}"
            )

    def test_cross_domain_customer_linking(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame,
        cross_domain_resolver: CrossDomainResolver
    ) -> None:
        """Test: Risk profile RDF links to customer IRIs via cross-domain resolver.

        Verifies:
        - Risk profiles reference customer IRIs minted by cross-domain resolver
        - Customer IRIs in RDF match cross-domain resolver output
        - Cross-domain linking is consistent
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        # Resolve customer IRI using cross-domain resolver
        expected_customer_iri = cross_domain_resolver.resolve_customer_iri(
            "john@acme.com",
            "kyc_12345"
        )

        # Query for risk profile-customer link in RDF
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?rp ?customer WHERE {
                ?rp fintech:riskProfileId "risk_001" ;
                    fintech:forCustomer ?customer .
            }
        """
        results = list(graph.query(query))

        assert len(results) > 0, (
            "Expected at least one risk profile-customer link in RDF"
        )

        # Verify the customer IRI matches what cross-domain resolver produced
        actual_customer_iri = str(results[0][1])

        assert actual_customer_iri == expected_customer_iri, (
            f"Risk profile should link to correct customer IRI. "
            f"Expected: {expected_customer_iri}, Got: {actual_customer_iri}"
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

    def test_multiple_risk_profiles_same_customer_single_iri(
        self,
        transformer: SilverToRdfTransformer,
        cross_domain_resolver: CrossDomainResolver
    ) -> None:
        """Test: Multiple risk profiles for same customer link to same customer IRI.

        Verifies:
        - Cross-domain linking produces single IRI per unique customer
        - Multiple risk profiles reference same customer IRI
        - Deduplication works correctly
        """
        # Create risk profiles data with duplicate customer
        risk_profiles_df = pd.DataFrame({
            'risk_id': ['risk_001', 'risk_002', 'risk_003'],
            'customer_email': [
                'john@acme.com',
                'john@acme.com',  # Same customer as risk_001
                'jane@techcorp.io'
            ],
            'customer_kyc_id': [
                'kyc_12345',
                'kyc_12345',  # Same customer as risk_001
                'kyc_67890'
            ],
            'risk_score': [0.92, 0.88, 0.45],
            'risk_level': ['HIGH', 'CRITICAL', 'LOW'],
            'compliance_status': ['UNDER_REVIEW', 'SUSPENDED', 'COMPLIANT'],
            'kyc_status': ['VERIFIED', 'REJECTED', 'VERIFIED'],
            'fraud_flags_count': [2, 5, 0],
            'last_review_date': [
                datetime(2026, 5, 20, 14, 30, 0),
                datetime(2026, 5, 17, 9, 30, 0),
                datetime(2026, 5, 18, 10, 15, 0)
            ],
            'next_review_date': [
                datetime(2026, 6, 20, 14, 30, 0),
                datetime(2026, 6, 17, 9, 30, 0),
                datetime(2026, 6, 18, 10, 15, 0)
            ],
            'review_notes': [
                'High transaction volume',
                'Account suspended',
                'Routine review'
            ]
        })

        transformer.transform_risk_profiles_to_rdf(risk_profiles_df)
        graph = transformer.get_graph()

        # Get the expected customer IRI
        expected_customer_iri = cross_domain_resolver.resolve_customer_iri(
            "john@acme.com",
            "kyc_12345"
        )

        # Query for all risk profile-customer links
        query_john = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?customer WHERE {
                ?rp fintech:riskProfileId ?rpId ;
                    fintech:forCustomer ?customer .
                FILTER (?rpId IN ("risk_001", "risk_002"))
            }
        """
        john_results = list(graph.query(query_john))

        assert len(john_results) == 2, (
            f"Expected 2 risk profiles for john@acme.com, got {len(john_results)}"
        )

        # Verify both risk profiles reference the same customer IRI
        customer_iri_1 = str(john_results[0][0])
        customer_iri_2 = str(john_results[1][0])

        assert customer_iri_1 == customer_iri_2, (
            f"Same customer should have same IRI: {customer_iri_1} != {customer_iri_2}"
        )

        assert customer_iri_1 == expected_customer_iri, (
            f"Customer IRI should match cross-domain resolver output. "
            f"Expected: {expected_customer_iri}, Got: {customer_iri_1}"
        )

    def test_metadata_source_system_tagging(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: All RDF triples have sourceSystem='risk_compliance' metadata.

        Verifies:
        - Risk profiles have sourceSystem metadata
        - sourceSystem value is 'risk_compliance' for all
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        results = list(graph.query(self._query_source_system_metadata()))

        assert len(results) > 0, (
            f"Expected sourceSystem metadata on entities. Graph has {len(graph)} total triples"
        )

        for result in results:
            system_value = str(result[1])
            assert system_value == "risk_compliance", (
                f"sourceSystem should be 'risk_compliance', got '{system_value}'. "
                f"Query returned {len(results)} metadata triples"
            )

    def test_metadata_ingestion_time_format(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: RDF triples include sourceIngestionTime with valid timestamp.

        Verifies:
        - sourceIngestionTime metadata is present
        - sourceIngestionTime values are valid ISO 8601 timestamps
        - At least one timestamp per entity
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        results = list(graph.query(self._query_ingestion_time_metadata()))

        assert len(results) > 0, (
            f"Expected sourceIngestionTime metadata on risk profiles. "
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

    def test_risk_level_enum_validation(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: Risk level enum only contains valid values (LOW, MEDIUM, HIGH, CRITICAL).

        Verifies:
        - All risk levels in transformed RDF are valid enum values
        - No invalid risk levels are present
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?riskLevel WHERE {
                ?rp fintech:riskLevel ?riskLevel .
            }
        """
        results = list(graph.query(query))

        valid_risk_levels = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

        assert len(results) > 0, (
            f"Expected risk levels in RDF, got none"
        )

        for result in results:
            risk_level = str(result[0])
            assert risk_level in valid_risk_levels, (
                f"Invalid risk level: {risk_level}. Must be one of {valid_risk_levels}"
            )

    def test_kyc_status_enum_validation(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: KYC status enum only contains valid values.

        Verifies:
        - All KYC statuses are from: NOT_STARTED, IN_PROGRESS, VERIFIED, REJECTED, EXPIRED
        - No invalid KYC statuses are present
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?kycStatus WHERE {
                ?rp fintech:kycStatus ?kycStatus .
            }
        """
        results = list(graph.query(query))

        valid_kyc_statuses = {"NOT_STARTED", "IN_PROGRESS", "VERIFIED", "REJECTED", "EXPIRED"}

        assert len(results) > 0, (
            f"Expected KYC statuses in RDF, got none"
        )

        for result in results:
            kyc_status = str(result[0])
            assert kyc_status in valid_kyc_statuses, (
                f"Invalid KYC status: {kyc_status}. Must be one of {valid_kyc_statuses}"
            )

    def test_compliance_status_enum_validation(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame
    ) -> None:
        """Test: Compliance status enum only contains valid values.

        Verifies:
        - All compliance statuses are from: COMPLIANT, UNDER_REVIEW, NON_COMPLIANT, SUSPENDED
        - No invalid compliance statuses are present
        """
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?complianceStatus WHERE {
                ?rp fintech:complianceStatus ?complianceStatus .
            }
        """
        results = list(graph.query(query))

        valid_compliance_statuses = {"COMPLIANT", "UNDER_REVIEW", "NON_COMPLIANT", "SUSPENDED"}

        assert len(results) > 0, (
            f"Expected compliance statuses in RDF, got none"
        )

        for result in results:
            compliance_status = str(result[0])
            assert compliance_status in valid_compliance_statuses, (
                f"Invalid compliance status: {compliance_status}. Must be one of {valid_compliance_statuses}"
            )

    def test_full_pipeline_end_to_end(
        self,
        transformer: SilverToRdfTransformer,
        sample_risk_profiles_df: pd.DataFrame,
        cross_domain_resolver: CrossDomainResolver
    ) -> None:
        """Test: Complete end-to-end pipeline from raw data to queryable RDF.

        Verifies:
        - Risk profiles transform to RDF
        - Cross-domain linking works
        - SPARQL queries execute successfully
        - Metadata is correct
        - Triple count is sufficient
        - Enum validation passes
        """
        # Step 1: Transform risk profiles
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Step 2: Get the RDF graph
        graph = transformer.get_graph()

        # Verify triple count
        assert len(graph) >= self.MIN_EXPECTED_TRIPLES, (
            f"Expected >= {self.MIN_EXPECTED_TRIPLES} total triples, got {len(graph)}"
        )

        # Step 3: Verify risk profile count via SPARQL
        rp_results = list(graph.query(self._count_risk_profiles_query()))
        rp_count = int(rp_results[0][0])

        assert rp_count >= self.MIN_RISK_PROFILES, (
            f"Expected >= {self.MIN_RISK_PROFILES} risk profiles in RDF, got {rp_count}"
        )

        # Step 4: Verify high risk profiles query works
        high_risk_results = list(graph.query(self._query_high_risk_profiles()))

        assert len(high_risk_results) >= 1, (
            f"Expected >= 1 HIGH/CRITICAL risk profile in RDF, got {len(high_risk_results)}"
        )

        # Step 5: Verify non-compliant profiles query works
        non_compliant_results = list(graph.query(self._query_non_compliant_customers()))

        assert len(non_compliant_results) >= 1, (
            f"Expected >= 1 NON_COMPLIANT/SUSPENDED profile in RDF, got {len(non_compliant_results)}"
        )

        # Step 6: Verify cross-domain linking
        customer_results = list(graph.query(self._query_customer_links()))

        assert len(customer_results) >= self.MIN_RISK_PROFILES, (
            f"Expected >= {self.MIN_RISK_PROFILES} risk profile-customer links, "
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
            assert str(result[1]) == "risk_compliance", (
                f"Expected sourceSystem='risk_compliance', got '{result[1]}'. "
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

        # Step 8: Verify enum validation for risk levels
        risk_levels_query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            SELECT ?riskLevel WHERE { ?rp fintech:riskLevel ?riskLevel . }
        """
        risk_level_results = list(graph.query(risk_levels_query))
        valid_risk_levels = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

        for result in risk_level_results:
            assert str(result[0]) in valid_risk_levels, (
                f"Invalid risk level: {result[0]}"
            )

        # Step 9: Verify enum validation for compliance status
        compliance_query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            SELECT ?status WHERE { ?rp fintech:complianceStatus ?status . }
        """
        compliance_results = list(graph.query(compliance_query))
        valid_statuses = {"COMPLIANT", "UNDER_REVIEW", "NON_COMPLIANT", "SUSPENDED"}

        for result in compliance_results:
            assert str(result[0]) in valid_statuses, (
                f"Invalid compliance status: {result[0]}"
            )

        # Step 10: Verify enum validation for KYC status
        kyc_query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            SELECT ?status WHERE { ?rp fintech:kycStatus ?status . }
        """
        kyc_results = list(graph.query(kyc_query))
        valid_kyc_statuses = {"NOT_STARTED", "IN_PROGRESS", "VERIFIED", "REJECTED", "EXPIRED"}

        for result in kyc_results:
            assert str(result[0]) in valid_kyc_statuses, (
                f"Invalid KYC status: {result[0]}"
            )
