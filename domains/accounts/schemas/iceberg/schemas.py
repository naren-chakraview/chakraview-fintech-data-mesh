from pyiceberg.types import StringType, DoubleType, TimestampType
from pyiceberg.schema import Schema
from pyiceberg.partitioning import PartitionSpec, PartitionField
from shared.schemas import IcebergSchemaBuilder


def accounts_schema() -> Schema:
    """Accounts table schema"""
    builder = IcebergSchemaBuilder("accounts", version="1.0")
    builder.add_field("account_id", StringType(), required=True)
    builder.add_field("customer_id", StringType(), required=True)
    builder.add_field("customer_name", StringType(), required=True)
    builder.add_field("account_type", StringType(), required=True)
    builder.add_field("currency", StringType(), required=True)
    builder.add_field("status", StringType(), required=True)
    builder.add_field("opened_date", TimestampType(), required=True)
    builder.add_field("last_updated", TimestampType(), required=True)
    return builder.build()


def account_balances_schema() -> Schema:
    """Account balances table schema"""
    builder = IcebergSchemaBuilder("account_balances", version="1.0")
    builder.add_field("account_id", StringType(), required=True)
    builder.add_field("balance", DoubleType(), required=True)
    builder.add_field("available_balance", DoubleType(), required=True)
    builder.add_field("snapshot_date", TimestampType(), required=True)
    return builder.build()


def accounts_schema_partitions() -> PartitionSpec:
    """Partitioning for accounts: [year, month, day]"""
    return PartitionSpec(
        PartitionField(source_id=7, field_id=1000, transform="year", name="year"),
        PartitionField(source_id=7, field_id=1001, transform="month", name="month"),
        PartitionField(source_id=7, field_id=1002, transform="day", name="day"),
    )
