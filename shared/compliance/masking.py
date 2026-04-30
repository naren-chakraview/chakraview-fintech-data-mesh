from typing import Dict, List, Optional
import hashlib


class DataMasker:
    """Column-level data masking for PII/sensitive data"""

    MASKING_STRATEGIES = {
        "pii": "hash_mask",
        "sensitive": "partial_mask",
        "confidential": "full_mask",
        "public": "no_mask",
    }

    @staticmethod
    def hash_mask(value: str, visible_chars: int = 4) -> str:
        """Hash mask: show first N chars, hash rest"""
        if not value or len(value) <= visible_chars:
            return "[MASKED]"
        visible = value[:visible_chars]
        hash_val = hashlib.sha256(value.encode()).hexdigest()[:8]
        return f"{visible}...{hash_val}"

    @staticmethod
    def partial_mask(value: str, visible_chars: int = 2) -> str:
        """Partial mask: show first/last N chars"""
        if not value or len(value) <= visible_chars * 2:
            return "[MASKED]"
        visible_start = value[:visible_chars]
        visible_end = value[-visible_chars:]
        masked_len = len(value) - (visible_chars * 2)
        return f"{visible_start}{'*' * masked_len}{visible_end}"

    @staticmethod
    def full_mask(value: str) -> str:
        """Full mask: replace entire value"""
        return "[MASKED]"

    @staticmethod
    def no_mask(value: str) -> str:
        """No masking"""
        return value


class ColumnMaskingPolicy:
    """Defines which columns to mask and how"""

    def __init__(self):
        self.policies: Dict[str, Dict[str, str]] = {}

    def add_policy(
        self,
        table: str,
        column: str,
        classification: str,
    ) -> None:
        """Add masking policy for column"""
        if table not in self.policies:
            self.policies[table] = {}
        self.policies[table][column] = classification

    def get_column_classification(self, table: str, column: str) -> Optional[str]:
        """Get column classification"""
        return self.policies.get(table, {}).get(column)

    def should_mask(self, table: str, column: str) -> bool:
        """Check if column should be masked"""
        classification = self.get_column_classification(table, column)
        return classification is not None and classification != "public"


FINTECH_MASKING_POLICIES = {
    "transactions.raw_transactions": {
        "account_id": "pii",
        "customer_name": "pii",
        "ssn": "confidential",
        "account_holder_name": "pii",
        "amount": "public",
        "merchant_id": "public",
        "timestamp": "public",
    },
    "accounts.account_balances": {
        "account_id": "pii",
        "customer_name": "pii",
        "balance": "sensitive",
        "currency": "public",
    },
    "risk_compliance.fraud_scores": {
        "account_id": "pii",
        "fraud_score": "sensitive",
        "risk_level": "public",
    },
}
