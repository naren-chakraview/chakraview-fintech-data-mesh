"""Cross-domain resolver for resolving Customer IRIs from Accounts domain.

Risk/Compliance domain does not own Customer IRIs.
Instead, it resolves Customer IRIs from Accounts domain using the same
deterministic hashing algorithm, ensuring deduplication across domains.
"""

import hashlib


class CrossDomainResolver:
    """Resolve Customer IRIs from Accounts domain."""

    def __init__(self, base_url: str = "https://chakracommerce.com"):
        self.base_url = base_url
        self.hash_algorithm = "sha256"
        self.hash_length = 8

    def _normalize(self, text: str) -> str:
        """Normalize text for IRI generation (lowercase + trim)"""
        return str(text).lower().strip()

    def _hash(self, text: str) -> str:
        """Generate stable hash from normalized text"""
        hash_obj = hashlib.sha256(text.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()
        return hash_hex[:self.hash_length]

    def resolve_customer_iri(self, customer_email: str, customer_kyc_id: str) -> str:
        """Resolve Customer IRI from Accounts domain.

        Uses identical normalization and hashing as Accounts domain
        to guarantee deduplication—same customer email+kyc_id
        always produces the same IRI.

        Args:
            customer_email: Customer email address
            customer_kyc_id: Customer KYC ID

        Returns:
            Customer IRI as minted by Accounts domain

        Example:
            ("JOHN@ACME.COM", "KYC_123")
            → "https://chakracommerce.com/customer#a1b2c3d4"

        Note:
            This must match the Accounts domain IRI exactly.
            If it doesn't, entity deduplication will fail.
        """
        # Normalize (same as Accounts domain)
        normalized_email = self._normalize(customer_email)
        normalized_kyc = self._normalize(customer_kyc_id)

        # Combine with separator
        combined = f"{normalized_email}|{normalized_kyc}"

        # Hash (same as Accounts domain)
        hash_prefix = self._hash(combined)

        # Return IRI (same format as Accounts domain)
        return f"{self.base_url}/customer#{hash_prefix}"
