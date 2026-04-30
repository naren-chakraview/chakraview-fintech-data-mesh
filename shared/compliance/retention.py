from typing import Dict, Optional


class RetentionPolicy:
    """Data retention policies for compliance"""

    def __init__(self):
        self.policies: Dict[str, int] = {}

    def add_policy(self, table: str, years: int, reason: str = "") -> None:
        """Add retention policy (years from creation)"""
        self.policies[table] = years

    def get_retention_years(self, table: str) -> Optional[int]:
        """Get retention period in years"""
        return self.policies.get(table)

    def get_retention_days(self, table: str) -> Optional[int]:
        """Get retention period in days"""
        years = self.get_retention_years(table)
        if years:
            return years * 365
        return None


FINTECH_RETENTION_POLICIES = {
    "transactions.raw_transactions": 7,
    "transactions.settlement_status": 7,
    "accounts.account_balances": 3,
    "risk_compliance.fraud_scores": 5,
    "risk_compliance.kyc_verdicts": 10,
    "counterparties.merchants": 2,
    "market_data.fx_rates": 1,
}


def build_retention_policy() -> RetentionPolicy:
    """Build retention policy from fintech config"""
    policy = RetentionPolicy()
    for table, years in FINTECH_RETENTION_POLICIES.items():
        policy.add_policy(table, years)
    return policy
