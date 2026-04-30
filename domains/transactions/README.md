# Transactions Domain

## Overview

The Transactions domain owns real-time transaction events, settlement records, and clearing status for all payment activity. This is the highest-volume, lowest-latency domain in the data mesh.

## Data Products

- **transaction-feed** — Real-time transaction events + settlement status
  - Tables: `raw_transactions`, `settlement_status`
  - Freshness: 5 minutes
  - Consumers: fraud detection, settlement reconciliation, compliance

## Architecture

### Ingest Pipeline

```
Kafka: transactions-raw
  ↓ [Spark Structured Streaming, 5-min batches]
  ↓ Schema validation (Avro v2.1)
  ↓ Deduplication (Kafka offset tracking)
  ↓ Error handling (DLQ for failures)
Iceberg: transactions.raw_transactions
  ↓ [Periodic compaction, daily]
```

### Schemas

- **Avro** (Kafka): `schemas/avro/transaction-v2.1.avsc`
- **Iceberg** (Lake): `schemas/iceberg/raw_transactions.schema`, `settlement_status.schema`

### Ingest Job

- **File**: `ingest/ingest_job.py`
- **Trigger**: Continuous Spark Structured Streaming
- **SLA**: 5-minute freshness, 99.9% availability

## Query Examples

- Transactions by account: `queries/transaction-by-account.sql`
- Settlement reconciliation: `queries/settlement-reconciliation.sql`
- Fraud scoring input: `queries/fraud-scoring-join.sql`

## Testing

- **Unit**: Schema validation, deduplication logic
- **Integration**: Kafka → Iceberg pipeline
- **Compliance**: PII masking, audit logging, retention

## Operational Runbooks

See `../../docs/domains/transactions/` for:
- Schema evolution process
- Troubleshooting ingest failures
- Compaction performance tuning
