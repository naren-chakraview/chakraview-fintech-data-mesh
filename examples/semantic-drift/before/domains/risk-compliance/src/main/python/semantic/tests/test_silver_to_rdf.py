"""Unit tests for Risk/Compliance domain Silver-to-RDF transformation."""

import pytest
import pandas as pd
import os
from datetime import datetime
from ..silver_to_rdf import SilverToRdfTransformer
from ..iri_resolver import IriResolver
from ..cross_domain_resolver import CrossDomainResolver


class TestSilverToRdfTransformer:
    """Test RDF transformation for risk profiles."""

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
    def sample_risk_profiles_df(self):
        """Sample risk profile data."""
        return pd.DataFrame({
            'risk_id': ['risk_001', 'risk_002', 'risk_003'],
            'customer_email': ['john@acme.com', 'jane@acme.com', 'bob@widgets.com'],
            'customer_kyc_id': ['kyc_9999', 'kyc_8888', 'kyc_7777'],
            'risk_score': [0.92, 0.45, 0.78],
            'risk_level': ['HIGH', 'LOW', 'MEDIUM'],
            'compliance_status': ['UNDER_REVIEW', 'COMPLIANT', 'NON_COMPLIANT'],
            'kyc_status': ['VERIFIED', 'VERIFIED', 'IN_PROGRESS'],
            'fraud_flags_count': [2, 0, 1],
            'last_review_date': [
                datetime(2026, 5, 20, 14, 30, 0),
                datetime(2026, 5, 15, 10, 0, 0),
                datetime(2026, 5, 25, 16, 45, 0)
            ],
            'next_review_date': [
                datetime(2026, 6, 20, 14, 30, 0),
                datetime(2026, 6, 15, 10, 0, 0),
                datetime(2026, 6, 25, 16, 45, 0)
            ],
            'review_notes': [
                'Customer flagged for high transaction volume',
                'Routine review - compliant',
                'Potential money laundering concerns'
            ]
        })

    def test_transform_risk_profiles_generates_triples(self, transformer, sample_risk_profiles_df):
        """Test: Silver risk profile data transforms to RDF triples."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Verify triples were generated (at least 10 per risk profile)
        assert len(graph) >= 30, f"Expected >= 30 triples for 3 risk profiles, got {len(graph)}"

    def test_rdf_type_declarations(self, transformer, sample_risk_profiles_df):
        """Test: All risk profiles have proper rdf:type declarations."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for RiskProfile type declarations
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT ?profile WHERE {
                ?profile rdf:type fintech:RiskProfile .
            }
        """
        results = list(graph.query(query))

        assert len(results) == 3, f"Expected 3 RiskProfile type declarations, got {len(results)}"

    def test_risk_profile_iri_format_in_rdf(self, transformer, sample_risk_profiles_df):
        """Test: Risk profile IRIs in RDF have correct format."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for risk profile IRIs
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT ?profile WHERE {
                ?profile rdf:type fintech:RiskProfile .
            }
        """
        results = list(graph.query(query))

        assert len(results) == 3, f"Expected 3 risk profiles, got {len(results)}"
        for result in results:
            assert str(result[0]).startswith("https://chakracommerce.com/risk-profile#"), \
                f"IRI format check: {result[0]}"

    def test_risk_profile_properties_present(self, transformer, sample_risk_profiles_df):
        """Test: Risk profile properties are correctly populated."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for risk profile properties
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?id ?score ?level ?status ?kyc_status ?flags WHERE {
                ?profile fintech:riskProfileId ?id ;
                         fintech:riskScore ?score ;
                         fintech:riskLevel ?level ;
                         fintech:complianceStatus ?status ;
                         fintech:kycStatus ?kyc_status ;
                         fintech:fraudFlagsCount ?flags .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 3, "Expected all risk profile properties to be present"

    def test_cross_domain_customer_linking(self, transformer, sample_risk_profiles_df):
        """Test: Risk profiles are linked to customer IRIs."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for risk profile-customer links
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT ?profile ?customer WHERE {
                ?profile rdf:type fintech:RiskProfile ;
                         fintech:forCustomer ?customer .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 3, f"Expected >= 3 risk profile-customer links, got {len(results)}"

    def test_metadata_source_system_tagging(self, transformer, sample_risk_profiles_df):
        """Test: Risk profile RDF triples include sourceSystem metadata."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for sourceSystem metadata
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?system WHERE {
                ?profile fintech:sourceSystem ?system .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 1, "Expected sourceSystem metadata on risk profiles"
        assert str(results[0][0]) == "risk_compliance", "sourceSystem should be 'risk_compliance'"

    def test_metadata_ingestion_time_format(self, transformer, sample_risk_profiles_df):
        """Test: Risk profile RDF includes sourceIngestionTime metadata."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for sourceIngestionTime metadata
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?time WHERE {
                ?profile fintech:sourceIngestionTime ?time .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 1, "Expected sourceIngestionTime metadata on risk profiles"
        # Should be a string in ISO format
        time_str = str(results[0][0])
        assert "T" in time_str, "Ingestion time should be in ISO format"

    def test_sparql_query_risk_profiles(self, transformer, sample_risk_profiles_df):
        """Test: SPARQL queries work on generated RDF."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for high-risk profiles
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?profile ?score ?level WHERE {
                ?profile fintech:riskScore ?score ;
                         fintech:riskLevel ?level .
                FILTER (?level = "HIGH")
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 1, "Expected at least 1 HIGH risk profile"

    def test_risk_level_values_validation(self, transformer, sample_risk_profiles_df):
        """Test: Risk level enum values are validated."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for distinct risk levels
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT DISTINCT ?level WHERE {
                ?profile fintech:riskLevel ?level .
            }
        """
        results = list(graph.query(query))
        risk_levels = {str(r[0]) for r in results}

        # Should match input data
        expected_levels = {"HIGH", "LOW", "MEDIUM"}
        assert risk_levels == expected_levels, f"Expected {expected_levels}, got {risk_levels}"

    def test_kyc_status_values_validation(self, transformer, sample_risk_profiles_df):
        """Test: KYC status enum values are present."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for distinct KYC statuses
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT DISTINCT ?status WHERE {
                ?profile fintech:kycStatus ?status .
            }
        """
        results = list(graph.query(query))
        kyc_statuses = {str(r[0]) for r in results}

        # Should match input data
        expected_statuses = {"VERIFIED", "IN_PROGRESS"}
        assert expected_statuses.issubset(kyc_statuses), \
            f"Expected {expected_statuses} in {kyc_statuses}"

    def test_compliance_status_values_validation(self, transformer, sample_risk_profiles_df):
        """Test: Compliance status enum values are present."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for distinct compliance statuses
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT DISTINCT ?status WHERE {
                ?profile fintech:complianceStatus ?status .
            }
        """
        results = list(graph.query(query))
        compliance_statuses = {str(r[0]) for r in results}

        # Should match input data
        expected_statuses = {"UNDER_REVIEW", "COMPLIANT", "NON_COMPLIANT"}
        assert expected_statuses == compliance_statuses, \
            f"Expected {expected_statuses}, got {compliance_statuses}"

    def test_risk_score_numeric_validation(self, transformer, sample_risk_profiles_df):
        """Test: Risk scores are numeric values."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for risk scores
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?score WHERE {
                ?profile fintech:riskScore ?score .
            }
        """
        results = list(graph.query(query))

        assert len(results) == 3, "Expected 3 risk scores"
        for result in results:
            score = float(result[0])
            assert 0 <= score <= 1, f"Risk score should be between 0 and 1, got {score}"

    def test_fraud_flags_count_integer_type(self, transformer, sample_risk_profiles_df):
        """Test: Fraud flags count are integer values."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for fraud flags count
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?flags WHERE {
                ?profile fintech:fraudFlagsCount ?flags .
            }
        """
        results = list(graph.query(query))

        assert len(results) == 3, "Expected 3 fraud flag counts"
        for result in results:
            flags = int(result[0])
            assert flags >= 0, f"Fraud flags count should be non-negative, got {flags}"

    def test_get_graph(self, transformer, sample_risk_profiles_df):
        """Test: Retrieving the RDF graph after transformation."""
        transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)
        graph = transformer.get_graph()

        assert graph is not None, "Graph should not be None"
        assert len(graph) > 0, "Graph should contain triples"

    def test_multiple_transformations_accumulate(self, transformer):
        """Test: Multiple transformations accumulate triples in same graph."""
        df1 = pd.DataFrame({
            'risk_id': ['risk_001'],
            'customer_email': ['john@acme.com'],
            'customer_kyc_id': ['kyc_9999'],
            'risk_score': [0.92],
            'risk_level': ['HIGH'],
            'compliance_status': ['UNDER_REVIEW'],
            'kyc_status': ['VERIFIED'],
            'fraud_flags_count': [2],
            'last_review_date': [datetime(2026, 5, 20, 14, 30, 0)],
            'next_review_date': [datetime(2026, 6, 20, 14, 30, 0)],
            'review_notes': ['First profile']
        })

        df2 = pd.DataFrame({
            'risk_id': ['risk_002'],
            'customer_email': ['jane@acme.com'],
            'customer_kyc_id': ['kyc_8888'],
            'risk_score': [0.45],
            'risk_level': ['LOW'],
            'compliance_status': ['COMPLIANT'],
            'kyc_status': ['VERIFIED'],
            'fraud_flags_count': [0],
            'last_review_date': [datetime(2026, 5, 15, 10, 0, 0)],
            'next_review_date': [datetime(2026, 6, 15, 10, 0, 0)],
            'review_notes': ['Second profile']
        })

        transformer.transform_risk_profiles_to_rdf(df1)
        transformer.transform_risk_profiles_to_rdf(df2)
        graph = transformer.get_graph()

        # Should have triples from both transformations
        assert len(graph) >= 20, f"Expected >= 20 total triples, got {len(graph)}"

    def test_null_handling_for_optional_fields(self, transformer):
        """Test: Null/missing optional fields are handled gracefully."""
        df_with_nulls = pd.DataFrame({
            'risk_id': ['risk_001', 'risk_002'],
            'customer_email': ['john@acme.com', 'jane@acme.com'],
            'customer_kyc_id': ['kyc_9999', 'kyc_8888'],
            'risk_score': [0.92, 0.45],
            'risk_level': ['HIGH', 'LOW'],
            'compliance_status': ['UNDER_REVIEW', 'COMPLIANT'],
            'kyc_status': ['VERIFIED', 'VERIFIED'],
            'fraud_flags_count': [2, 0],
            'last_review_date': [datetime(2026, 5, 20, 14, 30, 0), None],
            'next_review_date': [None, datetime(2026, 6, 15, 10, 0, 0)],
            'review_notes': ['First profile', None]
        })

        graph = transformer.transform_risk_profiles_to_rdf(df_with_nulls)

        # Should handle gracefully - at least 2 risk profile declarations
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

            SELECT (COUNT(?profile) as ?count) WHERE {
                ?profile rdf:type fintech:RiskProfile .
            }
        """
        results = list(graph.query(query))
        count = int(results[0][0])

        assert count == 2, f"Expected 2 risk profiles despite nulls, got {count}"

    def test_review_dates_in_correct_format(self, transformer, sample_risk_profiles_df):
        """Test: Review dates are stored in ISO format."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for review dates
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?last_date ?next_date WHERE {
                ?profile fintech:lastReviewDate ?last_date ;
                         fintech:nextReviewDate ?next_date .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 1, "Expected review dates to be present"
        for result in results:
            last_date_str = str(result[0])
            next_date_str = str(result[1])
            assert "T" in last_date_str, "Last review date should be in ISO format"
            assert "T" in next_date_str, "Next review date should be in ISO format"

    def test_customer_iri_hash_consistency(self, transformer, sample_risk_profiles_df):
        """Test: Customer IRIs use 8-character hash format."""
        graph = transformer.transform_risk_profiles_to_rdf(sample_risk_profiles_df)

        # Query for customer links
        query = """
            PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

            SELECT ?customer WHERE {
                ?profile fintech:forCustomer ?customer .
            }
        """
        results = list(graph.query(query))

        assert len(results) >= 3, "Expected customer links"
        for result in results:
            customer_iri = str(result[0])
            assert customer_iri.startswith("https://chakracommerce.com/customer#"), \
                f"Customer IRI format check: {customer_iri}"
            hash_part = customer_iri.split("#")[1]
            assert len(hash_part) == 8, \
                f"Customer hash should be 8 chars, got {len(hash_part)}: {hash_part}"
