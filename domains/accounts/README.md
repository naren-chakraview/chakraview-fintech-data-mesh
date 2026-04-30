# Accounts Domain

Master account data and real-time balances. Core reference for regulatory reporting and analytics.

## Data Products

- **account-master** — Account records + daily balance snapshots
  - Tables: `accounts`, `account_balances`
  - Freshness: 10 minutes
  - Retention: 3 years (regulatory requirement)

## Architecture

- Ingest: Spark Structured Streaming from Kafka (10-min batches)
- Storage: Iceberg tables partitioned by [year, month, day]
- SLA: 10-minute freshness, 99.95% availability
