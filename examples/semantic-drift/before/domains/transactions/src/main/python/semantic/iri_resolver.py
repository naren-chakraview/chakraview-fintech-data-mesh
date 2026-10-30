"""IRI resolver for Transactions domain entities (Transaction, Counterparty).

Transactions domain owns IRIs for:
- Transaction entities (globally unique transaction_id)
- Counterparty entities (globally unique counterparty_id)

Transactions domain does NOT own Customer IRIs (Accounts owns those).
Use CrossDomainResolver to lookup Customer IRIs from Accounts domain.
"""


class IriResolver:
    """Generate deterministic IRIs for Transaction and Counterparty entities."""

    def __init__(self, base_url: str = "https://chakracommerce.com"):
        self.base_url = base_url

    def _normalize(self, text: str) -> str:
        """Normalize text for IRI generation (lowercase + trim)"""
        return str(text).lower().strip()

    def mint_transaction_iri(self, transaction_id: str) -> str:
        """Mint IRI for Transaction entity.

        Transaction IDs are globally unique in source system.
        No hashing needed—direct identity-based format.

        Args:
            transaction_id: Source transaction identifier (e.g., "txn_001")

        Returns:
            Stable IRI for this transaction

        Example:
            "txn_001" → "https://chakracommerce.com/transaction#txn_001"
        """
        normalized_id = self._normalize(transaction_id)
        return f"{self.base_url}/transaction#{normalized_id}"

    def mint_counterparty_iri(self, counterparty_id: str) -> str:
        """Mint IRI for Counterparty entity.

        Counterparty IDs are globally unique.
        No hashing needed—direct identity-based format.

        Args:
            counterparty_id: Source counterparty identifier (e.g., "stripe")

        Returns:
            Stable IRI for this counterparty

        Example:
            "stripe" → "https://chakracommerce.com/counterparty#stripe"
        """
        normalized_id = self._normalize(counterparty_id)
        return f"{self.base_url}/counterparty#{normalized_id}"
