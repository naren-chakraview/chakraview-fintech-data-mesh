import pytest
from ..iri_resolver import IriResolver


class TestIriResolver:

    @pytest.fixture
    def resolver(self):
        return IriResolver()

    def test_mint_customer_iri_deterministic(self, resolver):
        """Test that same email + kyc_id produces same IRI"""
        iri1 = resolver.mint_customer_iri("john@acme.com", "kyc_123")
        iri2 = resolver.mint_customer_iri("john@acme.com", "kyc_123")
        assert iri1 == iri2

    def test_mint_customer_iri_case_insensitive(self, resolver):
        """Test that case variations in email and kyc_id produce same IRI"""
        iri1 = resolver.mint_customer_iri("john@acme.com", "KYC_123")
        iri2 = resolver.mint_customer_iri("JOHN@ACME.COM", "kyc_123")
        assert iri1 == iri2

    def test_mint_account_iri(self, resolver):
        """Test account IRI generation"""
        iri = resolver.mint_account_iri("acct_001")
        assert iri == "https://chakracommerce.com/account#acct_001"

    def test_mint_account_iri_case_insensitive(self, resolver):
        """Test that account IRI normalization is case-insensitive"""
        iri1 = resolver.mint_account_iri("ACCT_001")
        iri2 = resolver.mint_account_iri("acct_001")
        assert iri1 == iri2
