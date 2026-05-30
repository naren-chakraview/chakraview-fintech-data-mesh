import hashlib
from typing import Optional


class IriResolver:
    """Deterministic IRI minting for Accounts domain"""

    def __init__(self, base_url: str = "https://chakracommerce.com"):
        self.base_url = base_url

    def _normalize(self, text: str) -> str:
        """Normalize text for IRI generation (lowercase + trim)"""
        return str(text).lower().strip()

    def _hash(self, text: str) -> str:
        """Generate stable hash from normalized text"""
        return hashlib.sha256(text.encode()).hexdigest()[:8]

    def mint_customer_iri(self, email: str, kyc_id: str) -> str:
        """
        Mint stable IRI for customer based on email + kyc_id.
        Same email + kyc_id always produces same IRI (deterministic).
        """
        # Normalize both fields
        norm_email = self._normalize(email)
        norm_kyc = self._normalize(kyc_id)

        # Concatenate and hash
        combined = f"{norm_email}|{norm_kyc}"
        hash_id = self._hash(combined)

        return f"{self.base_url}/customer#{hash_id}"

    def mint_account_iri(self, account_id: str) -> str:
        """
        Mint IRI for account based on account_id.
        Account IDs are globally unique, so no cross-domain dedup needed.
        """
        norm_id = self._normalize(account_id)
        return f"{self.base_url}/account#{norm_id}"
