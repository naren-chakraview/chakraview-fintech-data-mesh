from pyiceberg.types import StringType, DoubleType, BooleanType, TimestampType
from pyiceberg.schema import Schema
from shared.schemas import IcebergSchemaBuilder


def fraud_scores_schema() -> Schema:
    """Fraud scores table schema"""
    builder = IcebergSchemaBuilder("fraud_scores", version="1.0")
    builder.add_field("transaction_id", StringType(), required=True)
    builder.add_field("account_id", StringType(), required=True)
    builder.add_field("fraud_score", DoubleType(), required=True)
    builder.add_field("risk_level", StringType(), required=True)
    builder.add_field("evaluated_at", TimestampType(), required=True)
    return builder.build()


def kyc_verdicts_schema() -> Schema:
    """KYC verdicts table schema"""
    builder = IcebergSchemaBuilder("kyc_verdicts", version="1.0")
    builder.add_field("account_id", StringType(), required=True)
    builder.add_field("kyc_status", StringType(), required=True)
    builder.add_field("sanctions_match", BooleanType(), required=True)
    builder.add_field("aml_flag", BooleanType(), required=True)
    builder.add_field("verified_at", TimestampType(), required=True)
    return builder.build()
