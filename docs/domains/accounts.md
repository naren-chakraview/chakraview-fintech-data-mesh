# Accounts Domain

Master data for customer accounts with balances, status, and account relationships.

---

## Overview

| Attribute | Value |
|-----------|-------|
| **Owner** | Accounts Domain Team |
| **Contact** | accounts@chakra.fintech |
| **Data Products** | account-master |
| **Kafka Topics** | accounts-raw (hot path) |
| **Iceberg Namespace** | accounts |
| **Freshness SLA** | 10 minutes |
| **Availability SLA** | 99.95% |
| **Retention** | 3 years |
| **Velocity** | Low (accounts change infrequently) |
| **Status** | Production |

---

## Data Products

### account-master

Customer account master data with real-time balance updates.

**Schema** (Avro v1.0):
```json
{
  "type": "record",
  "name": "Account",
  "fields": [
    {"name": "account_id", "type": "string"},
    {"name": "customer_id", "type": "string"},
    {"name": "customer_name", "type": "string"},
    {"name": "account_type", "type": {"type": "enum", "symbols": ["CHECKING", "SAVINGS", "MONEY_MARKET"]}},
    {"name": "currency", "type": "string"},
    {"name": "balance", "type": "double"},
    {"name": "available_balance", "type": "double"},
    {"name": "status", "type": {"type": "enum", "symbols": ["ACTIVE", "INACTIVE", "CLOSED"]}},
    {"name": "opened_date", "type": "long"},
    {"name": "last_updated", "type": "long"}
  ]
}
```

**Iceberg Table** (accounts.accounts):
- Partitions: [year, month]
- Format: Parquet (columnar)
- Snapshots: Every 10 minutes

**SLAs**:
```yaml
freshness:
  value: 10
  unit: minutes
  definition: "Account balance updates reflected within 10 minutes"

availability:
  value: 99.95
  unit: percent

completeness:
  value: 100
  unit: percent
```

**Quality Rules**:
```yaml
- name: positive_balance
  rule: "balance >= 0"
  impact: critical

- name: available_not_greater_than_balance
  rule: "available_balance <= balance"
  impact: critical

- name: valid_account_type
  rule: "account_type IN ('CHECKING', 'SAVINGS', 'MONEY_MARKET')"
  impact: high

- name: valid_status
  rule: "status IN ('ACTIVE', 'INACTIVE', 'CLOSED')"
  impact: medium
```

**Access Policy**:
```yaml
default: deny

approval_required: false

columns:
  - name: customer_id
    classification: pii
    masked_for_roles: [external_analyst]
    mask_strategy: full_hash

  - name: customer_name
    classification: pii
    masked_for_roles: [external_analyst]
    mask_strategy: first_letter_plus_hash

  - name: balance
    classification: sensitive
    masked_for_roles: [contractor]
    mask_strategy: no_mask

  - name: account_status
    classification: public
    masked_for_roles: []
```

**Downstream Consumers**:
```
account-reconciliation (Batch)
├── Queries: daily_account_balances
├── Purpose: Reconcile against general ledger
└── Frequency: Daily

account-risk-scoring (Real-time)
├── Queries: account.balance
├── Purpose: Risk model inputs (account velocity)
└── Frequency: Per transaction

reporting-portal (Batch)
├── Queries: All columns
├── Purpose: Customer reporting, statements
└── Frequency: Daily/weekly
```

---

## Ingest Pipeline

### Implementation

```python
# From domains/accounts/ingest/ingest_job.py

class AccountIngestJob:
    DOMAIN = "accounts"
    SOURCE_TOPIC = "accounts-raw"
    TARGET_TABLE = f"{DOMAIN}.accounts"

    def __init__(self, kafka_brokers: str, schema_registry_url: str, 
                 catalog_uri: str, warehouse: str):
        self.kafka_brokers = kafka_brokers
        self.catalog_uri = catalog_uri
        self.spark = SparkSession.builder \
            .appName("AccountIngest") \
            .config("spark.sql.catalog.rest", "org.apache.iceberg.spark.SparkCatalog") \
            .config("spark.sql.catalog.rest.type", "rest") \
            .config("spark.sql.catalog.rest.uri", catalog_uri) \
            .getOrCreate()
        self.catalog = IcebergCatalog(catalog_uri=catalog_uri, warehouse=warehouse)

    def run(self) -> None:
        try:
            self.catalog.create_namespace(self.DOMAIN)
            
            df = self.spark.readStream.format("kafka") \
                .option("kafka.bootstrap.servers", self.kafka_brokers) \
                .option("subscribe", self.SOURCE_TOPIC) \
                .option("startingOffsets", "latest") \
                .load()

            schema_str = '''{
                "account_id": "string",
                "customer_id": "string",
                "customer_name": "string",
                "account_type": "string",
                "currency": "string",
                "balance": "double",
                "available_balance": "double",
                "status": "string",
                "opened_date": "long",
                "last_updated": "long"
            }'''
            
            parsed_df = df.select(
                from_json(col("value").cast("string"), schema_of_json(schema_str))
                    .alias("data")
            ).select("data.*")

            # Use MERGE for updates (accounts change state)
            query = parsed_df.writeStream \
                .format("iceberg") \
                .mode("append") \
                .option("checkpointLocation", f"/tmp/checkpoint/{self.DOMAIN}") \
                .toTable(self.TARGET_TABLE)
            
            query.awaitTermination()
        except Exception as e:
            logger.error("Ingest job failed", error=e)
            raise
```

---

## Governance & Compliance

### Retention Policy

```
Accounts (active): Retain as long as account exists
Accounts (closed): 3 years after closure (regulatory requirement)

Reason: Banking regulations require maintaining account history 
for dispute resolution and compliance audits
```

### Balance Restatement Protocol

When a balance correction is needed:
```
1. Create new transaction in transactions.raw_transactions (ADJUSTMENT type)
2. Spark job includes adjustment in account-master
3. Time-travel query shows before/after state
4. Audit trail preserved (snapshot history)

Example:
├── Original balance on 2026-04-28: $10,000
├── Correction (overcharge detected): -$500
├── Adjusted balance: $9,500
├── Query time-travel to 2026-04-28 23:59:59: Shows $10,000
└── Query current (2026-04-30): Shows $9,500
```

---

## Querying

### Find High-Balance Accounts

```sql
SELECT customer_id, account_id, balance, account_type
FROM accounts.accounts
WHERE balance > 100000.00
  AND status = 'ACTIVE'
ORDER BY balance DESC
LIMIT 1000;
```

### Account Velocity (Risk Signal)

```sql
-- Join with transactions to compute account velocity
SELECT 
  a.account_id,
  a.customer_name,
  a.balance,
  COUNT(t.transaction_id) as transaction_count_7d,
  SUM(t.amount) as total_spent_7d,
  AVG(t.amount) as avg_transaction_amount,
  CASE 
    WHEN COUNT(t.transaction_id) > 50 THEN 'HIGH'
    WHEN COUNT(t.transaction_id) > 20 THEN 'MEDIUM'
    ELSE 'LOW'
  END as velocity_score
FROM accounts.accounts a
LEFT JOIN transactions.raw_transactions t
  ON a.account_id = t.account_id
  AND t.booking_timestamp > UNIX_TIMESTAMP() - 7*24*60*60
WHERE a.status = 'ACTIVE'
GROUP BY a.account_id, a.customer_name, a.balance;
```

---

## Comparison: Accounts vs Transactions

| Aspect | Transactions | Accounts |
|--------|--------------|----------|
| **Frequency** | Real-time (every second) | Low (minutes to hours) |
| **Size per update** | Small (1 record) | Medium (1 record) |
| **Query patterns** | Time-range scans (7 days) | Point lookups (current state) |
| **Retention** | 7 years (high volume) | 3 years (low volume) |
| **Iceberg SLA** | 5 minutes | 10 minutes |
| **Partitioning** | [year, month, day, account_id] | [year, month] |
| **Primary use** | Analytics, fraud detection | Reconciliation, reporting |

**Why different SLAs?** Accounts change infrequently; 10-min lag is acceptable. Transactions change constantly; 5-min lag needed for fraud detection.

---

## Scaling

```
Kafka topic: accounts-raw
├── Partitions: 2 (low velocity)
├── Replication: 3
└── Retention: 3 days

Spark job: AccountIngestJob
├── Executors: 1 (throughput is low)
├── Cores: 2
├── Memory: 2GB (small batches)
└── Batch size: Typically 100-500 records per 10-min window

Iceberg optimization:
├── Partition pruning by [year, month] is fast
├── Monthly scans are small (100GB total)
└── Compaction every 30 days (keep file count low)
```

---

## Next

- **[Risk/Compliance Domain](risk-compliance.md)** — Higher regulatory requirements
- **[Transactions Domain](transactions.md)** — Reference implementation (higher volume)
