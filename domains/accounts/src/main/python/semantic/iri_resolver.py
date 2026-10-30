"""IRI minting for the Accounts domain.

Customer IRIs come from the shared identity library (owned by Accounts):
shared/semantic/identity.py. Do not add a second copy of that rule here.
"""

from shared.semantic.identity import mint_customer_iri as _mint_customer_iri
from shared.semantic.identity import normalize


class IriResolver:
    """Deterministic IRI minting for Accounts domain"""

    def __init__(self, base_url: str = "https://chakracommerce.com"):
        self.base_url = base_url

    def _normalize(self, text: str) -> str:
        """Normalize text for IRI generation (lowercase + trim)"""
        return normalize(text)

    def mint_customer_iri(self, email: str, kyc_id: str) -> str:
        """
        Mint stable IRI for customer based on email + kyc_id.
        Same email + kyc_id always produces same IRI (deterministic).
        Requires FINTECH_IRI_KEY in the environment.
        """
        return _mint_customer_iri(email, kyc_id, base_url=self.base_url)

    def mint_account_iri(self, account_id: str) -> str:
        """
        Mint IRI for account based on account_id.
        Account IDs are globally unique, so no cross-domain dedup needed.
        """
        norm_id = self._normalize(account_id)
        return f"{self.base_url}/account#{norm_id}"
