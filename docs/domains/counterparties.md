# Counterparties Domain

Master data for merchants, payment processors, banks, and other counterparties. Low velocity reference data with moderate retention requirements.

---

## Overview

| Attribute | Value |
|-----------|-------|
| **Owner** | Counterparties Domain Team |
| **Contact** | counterparties@chakra.fintech |
| **Data Products** | partner-master |
| **Kafka Topics** | counterparties-raw |
| **Iceberg Namespace** | counterparties |
| **Freshness SLA** | 60 minutes |
| **Availability SLA** | 99.9% |
| **Retention** | 2 years |
| **Velocity** | Very low (reference data) |
| **Approval Required** | YES (commercial data) |
| **Status** | Production |

---

## Data Products

### partner-master

Master data for merchants, banks, payment processors, and other counterparties.

**Schema** (Avro v1.0):
```json
{
  "type": "record",
  "name": "Counterparty",
  "fields": [
    {"name": "counterparty_id", "type": "string"},
    {"name": "counterparty_type", "type": {"type": "enum", "symbols": ["MERCHANT", "BANK", "PROCESSOR", "PARTNER"]}},
    {"name": "counterparty_name", "type": "string"},
    {"name": "merchant_category_code", "type": ["null", "string"]},
    {"name": "credit_limit", "type": "double"},
    {"name": "settlement_period", "type": "int"},
    {"name": "fee_percentage", "type": "double"},
    {"name": "status", "type": {"type": "enum", "symbols": ["ACTIVE", "INACTIVE", "SUSPENDED"]}}
  ]
}
```

**Iceberg Table** (counterparties.merchants):
- Partitions: [year, month]
- Format: Parquet
- Snapshots: Every 60 minutes

**SLAs**:
```yaml
freshness:
  value: 60
  unit: minutes
  definition: "Merchant master data updates within 1 hour"

availability:
  value: 99.9
  unit: percent

completeness:
  value: 100
  unit: percent
```

**Quality Rules**:
```yaml
- name: positive_credit_limit
  rule: "credit_limit > 0"
  impact: critical

- name: valid_fee_percentage
  rule: "fee_percentage >= 0 AND fee_percentage <= 0.5"
  impact: high

- name: valid_settlement_period
  rule: "settlement_period IN (0, 1, 2, 3)"
  impact: high
  comment: "Settlement periods: 0=same-day, 1=next-day, 2=two-day, 3=three-day"

- name: mcc_format_if_merchant
  rule: "counterparty_type != 'MERCHANT' OR merchant_category_code LIKE '[0-9]{4}'"
  impact: medium
```

**Access Policy**:
```yaml
default: deny

approval_required: true
approval_sla_hours: 4

columns:
  - name: credit_limit
    classification: confidential
    masked_for_roles: [contractor, external_analyst]
    mask_strategy: full_mask  # Don't show limits to non-authorized users

  - name: fee_percentage
    classification: confidential
    masked_for_roles: [contractor]
    mask_strategy: full_mask

  - name: counterparty_name
    classification: public
    masked_for_roles: []
```

**Downstream Consumers**:
```
transaction-processing (Real-time)
├── Consumes: Kafka topic counterparties-raw (hot path)
├── Purpose: Route transactions to correct processor
└── SLA: < 100ms lookup

settlement-engine (Batch)
├── Consumes: Iceberg table counterparties.merchants
├── Purpose: Apply correct settlement terms and fees
└── Frequency: Daily

analytics-reporting (Batch)
├── Consumes: Iceberg table
├── Purpose: Counterparty performance analysis
└── Frequency: Weekly/monthly
```

---

## Ingest Pipeline

```python
# From domains/counterparties/ingest/ingest_job.py

class CounterpartyIngestJob:
    DOMAIN = "counterparties"
    SOURCE_TOPIC = "counterparties-raw"
    TARGET_TABLE = f"{DOMAIN}.merchants"

    def run(self) -> None:
        try:
            self.catalog.create_namespace(self.DOMAIN)
            
            df = self.spark.readStream.format("kafka") \
                .option("kafka.bootstrap.servers", self.kafka_brokers) \
                .option("subscribe", self.SOURCE_TOPIC) \
                .option("startingOffsets", "latest") \
                .load()

            schema_str = '''{
                "counterparty_id": "string",
                "counterparty_type": "string",
                "counterparty_name": "string",
                "merchant_category_code": "string",
                "credit_limit": "double",
                "settlement_period": "int",
                "fee_percentage": "double",
                "status": "string"
            }'''
            
            parsed_df = df.select(
                from_json(col("value").cast("string"), schema_of_json(schema_str))
                    .alias("data")
            ).select("data.*")

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
Counterparty Master: 2 years
├── Rationale: Reference data, inactive counterparties archive
├── Retention starts: From last transaction (3-year rule: if no activity, mark inactive)
└── Deletion process: Hard delete after 2 years of inactivity
```

### Approval Workflow for Commercial Data

```
User: "I need counterparty credit limits to audit exposure"

OPA Evaluation:
├── User role: auditor
├── Data classification: confidential (credit_limit)
├── Auto-approve? NO
├── Route to: Counterparty Domain Owner (transactions@chakra.fintech)
├── SLA: 4 hours

Owner decision:
├── Context review: Purpose? Justification?
├── Accept: Grant access (masking rules may still apply)
└── Reject: Deny (explain why)
```

---

## Queries

### Find High-Risk Merchants

```sql
-- Merchants with high credit limits and recent suspicious activity
SELECT 
  c.counterparty_id,
  c.counterparty_name,
  c.credit_limit,
  c.status,
  COUNT(t.transaction_id) as transaction_count_24h,
  SUM(t.amount) as total_amount_24h,
  AVG(r.fraud_score) as avg_fraud_score
FROM counterparties.merchants c
LEFT JOIN transactions.raw_transactions t
  ON c.counterparty_id = t.merchant_id
  AND t.booking_timestamp > UNIX_TIMESTAMP() - 24*60*60
LEFT JOIN risk_compliance.fraud_scores r
  ON t.transaction_id = r.transaction_id
WHERE c.credit_limit > 50000.00
  AND c.status = 'ACTIVE'
GROUP BY c.counterparty_id, c.counterparty_name, c.credit_limit, c.status
HAVING avg_fraud_score > 0.5
ORDER BY avg_fraud_score DESC;
```

### Settlement Reconciliation

```sql
-- Reconcile settled amounts against counterparty master terms
SELECT 
  c.counterparty_id,
  c.counterparty_name,
  c.settlement_period,
  c.fee_percentage,
  COUNT(t.transaction_id) as transaction_count,
  SUM(t.amount) as gross_amount,
  ROUND(SUM(t.amount) * (c.fee_percentage / 100.0), 2) as fees,
  ROUND(SUM(t.amount) * (1 - c.fee_percentage / 100.0), 2) as net_settlement
FROM counterparties.merchants c
INNER JOIN transactions.raw_transactions t
  ON c.counterparty_id = t.merchant_id
  AND t.status = 'CLEARED'
WHERE CURRENT_DATE - INTERVAL t.booking_timestamp < c.settlement_period
GROUP BY c.counterparty_id, c.counterparty_name, c.settlement_period, c.fee_percentage;
```

---

## Comparison: Reference Data vs Event Data

| Aspect | Counterparties (Reference) | Transactions (Events) |
|--------|---------------------------|------------------------|
| **Change frequency** | Hourly to daily | Real-time |
| **Size per update** | 1-100 records | 1 record |
| **Query patterns** | Point lookups (merchant details) | Time-range scans |
| **Retention** | 2 years | 7 years |
| **Freshness SLA** | 60 minutes | 5 minutes |
| **Partitioning** | [year, month] | [year, month, day, account_id] |
| **Snapshot frequency** | Hourly | Every 5 min |

---

## Scaling

```
Kafka topic: counterparties-raw
├── Partitions: 1 (very low volume, < 100 updates/hour)
├── Replication: 3
└── Retention: 2 days

Spark job: CounterpartyIngestJob
├── Executors: 1 (minimal parallelism needed)
├── Cores: 1
├── Memory: 1GB
└── Batch size: Typically 10-50 records per hour

Iceberg optimization:
├── Small table (< 10GB total)
├── Simple partition scheme [year, month]
└── Compaction: Yearly (consolidate annual files)
```

---

## Next

- **[Market Data Domain](market-data.md)** — High-frequency pricing feeds
- **[Transactions Domain](transactions.md)** — Reference implementation (compare velocities)
