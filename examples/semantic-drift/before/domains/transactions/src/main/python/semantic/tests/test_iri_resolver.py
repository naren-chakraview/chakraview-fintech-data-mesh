"""Unit tests for Transactions domain IRI resolver."""

import pytest
from ..iri_resolver import IriResolver


class TestIriResolver:
    """Test IRI resolver for Transaction and Counterparty entities."""

    @pytest.fixture
    def resolver(self):
        """Create IRI resolver instance."""
        return IriResolver()

    def test_mint_transaction_iri_deterministic(self, resolver):
        """Test: Transaction IRIs are deterministically minted."""
        iri1 = resolver.mint_transaction_iri("txn_001")
        iri2 = resolver.mint_transaction_iri("txn_001")

        assert iri1 == iri2, "Same transaction ID must produce same IRI"
        assert iri1.startswith("https://chakracommerce.com/transaction#"), "IRI format check"

    def test_mint_transaction_iri_case_insensitive(self, resolver):
        """Test: Transaction IRI minting is case-insensitive."""
        iri1 = resolver.mint_transaction_iri("TXN_001")
        iri2 = resolver.mint_transaction_iri("txn_001")

        assert iri1 == iri2, "Case should not affect IRI"

    def test_mint_counterparty_iri_deterministic(self, resolver):
        """Test: Counterparty IRIs are deterministically minted."""
        iri1 = resolver.mint_counterparty_iri("stripe")
        iri2 = resolver.mint_counterparty_iri("stripe")

        assert iri1 == iri2, "Same counterparty ID must produce same IRI"
        assert iri1.startswith("https://chakracommerce.com/counterparty#"), "IRI format check"

    def test_mint_counterparty_iri_case_insensitive(self, resolver):
        """Test: Counterparty IRI minting is case-insensitive."""
        iri1 = resolver.mint_counterparty_iri("STRIPE")
        iri2 = resolver.mint_counterparty_iri("stripe")

        assert iri1 == iri2, "Case should not affect IRI"

    def test_transaction_iri_format(self, resolver):
        """Test: Transaction IRI format is correct."""
        iri = resolver.mint_transaction_iri("txn_001")

        assert iri == "https://chakracommerce.com/transaction#txn_001", "Exact format match"

    def test_counterparty_iri_format(self, resolver):
        """Test: Counterparty IRI format is correct."""
        iri = resolver.mint_counterparty_iri("stripe")

        assert iri == "https://chakracommerce.com/counterparty#stripe", "Exact format match"

    def test_transaction_iri_with_whitespace(self, resolver):
        """Test: Transaction IRI handles whitespace normalization."""
        iri1 = resolver.mint_transaction_iri("  txn_001  ")
        iri2 = resolver.mint_transaction_iri("txn_001")

        assert iri1 == iri2, "Whitespace should be trimmed"

    def test_counterparty_iri_with_whitespace(self, resolver):
        """Test: Counterparty IRI handles whitespace normalization."""
        iri1 = resolver.mint_counterparty_iri("  STRIPE  ")
        iri2 = resolver.mint_counterparty_iri("stripe")

        assert iri1 == iri2, "Whitespace should be trimmed"

    def test_different_transactions_produce_different_iris(self, resolver):
        """Test: Different transaction IDs produce different IRIs."""
        iri1 = resolver.mint_transaction_iri("txn_001")
        iri2 = resolver.mint_transaction_iri("txn_002")

        assert iri1 != iri2, "Different transaction IDs must produce different IRIs"

    def test_different_counterparties_produce_different_iris(self, resolver):
        """Test: Different counterparty IDs produce different IRIs."""
        iri1 = resolver.mint_counterparty_iri("stripe")
        iri2 = resolver.mint_counterparty_iri("paypal")

        assert iri1 != iri2, "Different counterparty IDs must produce different IRIs"

    def test_custom_base_url(self):
        """Test: Custom base URL is respected."""
        custom_resolver = IriResolver(base_url="https://example.com")
        iri = custom_resolver.mint_transaction_iri("txn_001")

        assert iri.startswith("https://example.com/transaction#"), "Custom base URL should be used"
