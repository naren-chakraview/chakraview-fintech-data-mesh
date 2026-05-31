"""IRI resolver for Risk/Compliance domain entities (RiskProfile).

Risk/Compliance domain owns IRIs for:
- RiskProfile entities (globally unique risk_id)

Risk/Compliance domain does NOT own Customer IRIs (Accounts owns those).
Use CrossDomainResolver to lookup Customer IRIs from Accounts domain.
"""


class IriResolver:
    """Generate deterministic IRIs for RiskProfile entities."""

    def __init__(self, base_url: str = "https://chakracommerce.com"):
        self.base_url = base_url

    def _normalize(self, text: str) -> str:
        """Normalize text for IRI generation (lowercase + trim)"""
        return str(text).lower().strip()

    def mint_risk_profile_iri(self, risk_id: str) -> str:
        """Mint IRI for RiskProfile entity.

        Risk profile IDs are globally unique in source system.
        No hashing needed—direct identity-based format.

        Args:
            risk_id: Source risk profile identifier (e.g., "risk_001")

        Returns:
            Stable IRI for this risk profile

        Example:
            "risk_001" → "https://chakracommerce.com/risk-profile#risk_001"
        """
        normalized_id = self._normalize(risk_id)
        return f"{self.base_url}/risk-profile#{normalized_id}"
