"""Cross-domain resolver for resolving Customer IRIs from Accounts domain.

Risk/Compliance domain does not own Customer IRIs.
Instead, it resolves Customer IRIs from Accounts domain using the same
deterministic hashing algorithm, ensuring deduplication across domains.
"""

from shared.semantic.identity import mint_customer_iri


class CrossDomainResolver:
    """Resolve Customer IRIs minted by the Accounts domain.

    Delegates to shared/semantic/identity.py, so this domain cannot drift
    from Accounts. Requires FINTECH_IRI_KEY in the environment.
    """

    def __init__(self, base_url: str = "https://chakracommerce.com"):
        self.base_url = base_url

    def resolve_customer_iri(self, customer_email: str, customer_kyc_id: str) -> str:
        """Resolve Customer IRI from Accounts domain.

        Args:
            customer_email: Customer email address
            customer_kyc_id: Customer KYC ID

        Returns:
            Customer IRI as minted by the shared identity library
        """
        return mint_customer_iri(customer_email, customer_kyc_id, base_url=self.base_url)
