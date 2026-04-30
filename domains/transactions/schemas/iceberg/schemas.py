from pyiceberg.types import (
    StringType,
    DoubleType,
    TimestampType,
)
from pyiceberg.schema import Schema
from pyiceberg.partitioning import PartitionSpec, PartitionField
from shared.schemas import IcebergSchemaBuilder


def raw_transactions_schema() -> Schema:
    """Raw transactions table schema"""
    builder = IcebergSchemaBuilder(
        "raw_transactions",
        version="2.1",
    )

    builder.add_field("transaction_id", StringType(), required=True)
    builder.add_field("account_id", StringType(), required=True)
    builder.add_field("account_holder_name", StringType(), required=True)
    builder.add_field("amount", DoubleType(), required=True)
    builder.add_field("currency", StringType(), required=True)
    builder.add_field("merchant_id", StringType(), required=True)
    builder.add_field("merchant_category_code", StringType(), required=False)
    builder.add_field("booking_timestamp", TimestampType(), required=True)
    builder.add_field("settlement_timestamp", TimestampType(), required=False)
    builder.add_field("transaction_type", StringType(), required=True)
    builder.add_field("status", StringType(), required=True)

    return builder.build()


def raw_transactions_schema_partitions() -> PartitionSpec:
    """Partitioning for raw_transactions: [year, month, day, account_id]"""
    return PartitionSpec(
        PartitionField(
            source_id=8,
            field_id=1000,
            transform="year",
            name="booking_year",
        ),
        PartitionField(
            source_id=8,
            field_id=1001,
            transform="month",
            name="booking_month",
        ),
        PartitionField(
            source_id=8,
            field_id=1002,
            transform="day",
            name="booking_day",
        ),
        PartitionField(
            source_id=2,
            field_id=1003,
            transform="identity",
            name="account_id_part",
        ),
    )


def settlement_status_schema() -> Schema:
    """Settlement status table schema"""
    builder = IcebergSchemaBuilder(
        "settlement_status",
        version="1.0",
    )

    builder.add_field("transaction_id", StringType(), required=True)
    builder.add_field("status", StringType(), required=True)
    builder.add_field("booking_timestamp", TimestampType(), required=True)
    builder.add_field("settlement_timestamp", TimestampType(), required=False)
    builder.add_field("clearing_status", StringType(), required=False)
    builder.add_field("failure_reason", StringType(), required=False)

    return builder.build()


def settlement_status_schema_partitions() -> PartitionSpec:
    """Partitioning for settlement_status: [year, month, day]"""
    return PartitionSpec(
        PartitionField(
            source_id=3,
            field_id=2000,
            transform="year",
            name="booking_year",
        ),
        PartitionField(
            source_id=3,
            field_id=2001,
            transform="month",
            name="booking_month",
        ),
        PartitionField(
            source_id=3,
            field_id=2002,
            transform="day",
            name="booking_day",
        ),
    )
