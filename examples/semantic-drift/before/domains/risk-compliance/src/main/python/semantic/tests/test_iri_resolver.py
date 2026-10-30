"""Unit tests for Risk/Compliance domain IRI resolver."""

import pytest
from ..iri_resolver import IriResolver


class TestIriResolver:
    """Test IRI resolver for RiskProfile entities."""

    @pytest.fixture
    def resolver(self):
        """Create IRI resolver instance."""
        return IriResolver()

    def test_mint_risk_profile_iri_deterministic(self, resolver):
        """Test: Risk profile IRIs are deterministically minted."""
        iri1 = resolver.mint_risk_profile_iri("risk_001")
        iri2 = resolver.mint_risk_profile_iri("risk_001")

        assert iri1 == iri2, "Same risk ID must produce same IRI"
        assert iri1.startswith("https://chakracommerce.com/risk-profile#"), "IRI format check"

    def test_mint_risk_profile_iri_case_insensitive(self, resolver):
        """Test: Risk profile IRI minting is case-insensitive."""
        iri1 = resolver.mint_risk_profile_iri("RISK_001")
        iri2 = resolver.mint_risk_profile_iri("risk_001")

        assert iri1 == iri2, "Case should not affect IRI"

    def test_risk_profile_iri_format(self, resolver):
        """Test: Risk profile IRI format is correct."""
        iri = resolver.mint_risk_profile_iri("risk_001")

        assert iri == "https://chakracommerce.com/risk-profile#risk_001", "Exact format match"

    def test_mint_risk_profile_iri_with_whitespace(self, resolver):
        """Test: Risk profile IRI handles whitespace normalization."""
        iri1 = resolver.mint_risk_profile_iri("  risk_001  ")
        iri2 = resolver.mint_risk_profile_iri("risk_001")

        assert iri1 == iri2, "Whitespace should be trimmed"

    def test_different_risk_profiles_produce_different_iris(self, resolver):
        """Test: Different risk IDs produce different IRIs."""
        iri1 = resolver.mint_risk_profile_iri("risk_001")
        iri2 = resolver.mint_risk_profile_iri("risk_002")

        assert iri1 != iri2, "Different risk IDs must produce different IRIs"

    def test_risk_profile_iri_with_special_chars(self, resolver):
        """Test: Risk profile IRI with special characters in ID."""
        iri = resolver.mint_risk_profile_iri("RISK_2026-05-30_HIGH")

        assert iri.startswith("https://chakracommerce.com/risk-profile#"), "IRI format check"
        assert "risk_2026-05-30_high" in iri, "Special chars should be normalized"

    def test_risk_profile_iri_with_numbers(self, resolver):
        """Test: Risk profile IRI with numeric suffixes."""
        iri1 = resolver.mint_risk_profile_iri("risk_12345")
        iri2 = resolver.mint_risk_profile_iri("risk_12345")

        assert iri1 == iri2, "Numeric IDs should be handled consistently"

    def test_risk_profile_iri_empty_string_handling(self, resolver):
        """Test: Risk profile IRI with empty string gets normalized."""
        iri1 = resolver.mint_risk_profile_iri("  ")
        iri2 = resolver.mint_risk_profile_iri("")

        assert iri1 == iri2, "Empty/whitespace-only strings should produce same IRI"

    def test_risk_profile_iri_mixed_case(self, resolver):
        """Test: Risk profile IRI with mixed case normalization."""
        iri1 = resolver.mint_risk_profile_iri("RiSk_OoL")
        iri2 = resolver.mint_risk_profile_iri("risk_ool")

        assert iri1 == iri2, "Mixed case should normalize to lowercase"

    def test_custom_base_url(self):
        """Test: Custom base URL is respected."""
        custom_resolver = IriResolver(base_url="https://example.com")
        iri = custom_resolver.mint_risk_profile_iri("risk_001")

        assert iri.startswith("https://example.com/risk-profile#"), "Custom base URL should be used"
        assert iri == "https://example.com/risk-profile#risk_001", "Exact format with custom URL"
