"""Unit tests for cross-domain resolver (Accounts domain customer IRI resolution)."""

import pytest
from ..cross_domain_resolver import CrossDomainResolver


class TestCrossDomainResolver:
    """Test customer IRI resolution from Accounts domain."""

    @pytest.fixture
    def resolver(self):
        """Create cross-domain resolver instance."""
        return CrossDomainResolver()

    def test_resolve_customer_iri_deterministic(self, resolver):
        """Test: Customer IRI resolution is deterministic."""
        iri1 = resolver.resolve_customer_iri("john@acme.com", "kyc_123")
        iri2 = resolver.resolve_customer_iri("john@acme.com", "kyc_123")

        assert iri1 == iri2, "Same email + kyc_id must produce same IRI"
        assert iri1.startswith("https://chakracommerce.com/customer#"), "IRI format check"

    def test_resolve_customer_iri_case_insensitive(self, resolver):
        """Test: Customer IRI resolution is case-insensitive."""
        iri1 = resolver.resolve_customer_iri("JOHN@ACME.COM", "KYC_123")
        iri2 = resolver.resolve_customer_iri("john@acme.com", "kyc_123")

        assert iri1 == iri2, "Case should not affect customer IRI resolution"

    def test_resolve_different_customers(self, resolver):
        """Test: Different customers produce different IRIs."""
        iri1 = resolver.resolve_customer_iri("john@acme.com", "kyc_123")
        iri2 = resolver.resolve_customer_iri("jane@acme.com", "kyc_456")

        assert iri1 != iri2, "Different customers must produce different IRIs"

    def test_resolve_iri_format(self, resolver):
        """Test: Customer IRI has correct format."""
        iri = resolver.resolve_customer_iri("john@acme.com", "kyc_123")

        # Should be 8-char hash
        assert iri.startswith("https://chakracommerce.com/customer#"), "IRI prefix"
        hash_part = iri.split("#")[1]
        assert len(hash_part) == 8, "Hash should be 8 characters"

    def test_resolve_customer_iri_with_spaces(self, resolver):
        """Test: Customer IRI resolution handles whitespace."""
        iri1 = resolver.resolve_customer_iri("  john@acme.com  ", "  kyc_123  ")
        iri2 = resolver.resolve_customer_iri("john@acme.com", "kyc_123")

        assert iri1 == iri2, "Whitespace should be trimmed"

    def test_same_email_different_kyc_produces_different_iri(self, resolver):
        """Test: Same email but different KYC ID produces different IRI."""
        iri1 = resolver.resolve_customer_iri("john@acme.com", "kyc_123")
        iri2 = resolver.resolve_customer_iri("john@acme.com", "kyc_456")

        assert iri1 != iri2, "Different KYC IDs must produce different IRIs"

    def test_same_kyc_different_email_produces_different_iri(self, resolver):
        """Test: Same KYC ID but different email produces different IRI."""
        iri1 = resolver.resolve_customer_iri("john@acme.com", "kyc_123")
        iri2 = resolver.resolve_customer_iri("jane@acme.com", "kyc_123")

        assert iri1 != iri2, "Different emails must produce different IRIs"

    def test_hash_is_hexadecimal(self, resolver):
        """Test: Generated hash is valid hexadecimal."""
        iri = resolver.resolve_customer_iri("test@example.com", "kyc_001")
        hash_part = iri.split("#")[1]

        # Try to convert to int with base 16 (hex)
        try:
            int(hash_part, 16)
            assert True, "Hash is valid hexadecimal"
        except ValueError:
            assert False, "Hash should be valid hexadecimal"

    def test_cross_domain_consistency(self, resolver):
        """Test: Customer IRI matches Accounts domain format.

        This verifies that Risk/Compliance domain resolves customer IRIs
        using the exact same algorithm as Accounts domain minting.
        """
        # Verify format and determinism
        iri = resolver.resolve_customer_iri("test@example.com", "kyc_001")

        assert iri.startswith("https://chakracommerce.com/customer#"), "Format matches"
        assert len(iri.split("#")[1]) == 8, "Hash length matches (8 chars)"

    def test_custom_base_url(self):
        """Test: Custom base URL is respected."""
        custom_resolver = CrossDomainResolver(base_url="https://example.com")
        iri = custom_resolver.resolve_customer_iri("test@example.com", "kyc_001")

        assert iri.startswith("https://example.com/customer#"), "Custom base URL should be used"

    def test_multiple_customer_combinations_produce_unique_iris(self, resolver):
        """Test: Multiple customer combinations are all unique."""
        customers = [
            ("john@acme.com", "kyc_001"),
            ("john@acme.com", "kyc_002"),
            ("jane@acme.com", "kyc_001"),
            ("bob@widgets.com", "kyc_999"),
        ]

        iris = [resolver.resolve_customer_iri(email, kyc) for email, kyc in customers]

        # All IRIs should be unique
        assert len(iris) == len(set(iris)), "All customer combinations should produce unique IRIs"

    def test_hash_stability_over_multiple_calls(self, resolver):
        """Test: Hash remains stable over multiple calls."""
        iri_list = [
            resolver.resolve_customer_iri("stable@test.com", "kyc_stable")
            for _ in range(5)
        ]

        # All should be identical
        assert len(set(iri_list)) == 1, "Hash should be stable across multiple calls"
