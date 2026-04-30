# ADR-0002: Apache Iceberg as Lakehouse Storage

**Status**: Accepted | **Date**: 2026-04-05

---

## Context

The data mesh pattern requires storage that supports:
1. **Schema evolution without rewrites** (domains add columns independently)
2. **ACID transactions** (exactly-once ingest, no duplicates)
3. **Time-travel** (audit trails for compliance)
4. **Cost optimization** (7-year retention is expensive)
5. **Concurrent writes** (multiple domains writing in parallel)

Traditional Parquet + Hive metastore struggles with schema changes (requires full rewrite). Delta Lake (Databricks) is proprietary.

---

## Decision

**Choose Apache Iceberg** as the lakehouse storage format.

### Key Features Used
```
Iceberg provides:
├── Schema evolution (add/drop/rename columns without rewrite)
├── ACID transactions (atomic snapshot commits)
├── Time-travel (query historical snapshots for audits)
├── Partition pruning (cost-optimized scans)
├── Hidden partitions (abstraction over partition scheme)
└── Compatibility (works with Spark, Trino, Flink)
```

---

## Rationale

### Schema Evolution Without Rewrites
**Scenario**: Transactions domain wants to add `fraud_risk_score` column.

**Iceberg approach**:
- Create new schema version in metadata
- New writes include the column
- Old data implicitly gets NULL
- No rewrite, no downtime → 5-minute update

**Parquet approach**:
- Read all 7 years of data
- Rewrite with new column
- 8-hour job, 500GB rewrite cost
- Downtime during rewrite

### ACID & Exactly-Once
**Scenario**: Spark micro-batch job crashes after writing data but before recording offset.

**Iceberg approach**:
- Write to temp files
- Create atomic snapshot commit (one operation)
- Job crashes → temp files discarded, snapshot not updated
- Restart reads from last saved offset (checkpoint)
- Result: No duplicates ✅

**Parquet approach**:
- Data files written directly (visible immediately)
- Job crashes during commit
- Restart reads Kafka from beginning
- Result: Duplicates ❌ (need deduplication logic)

### Cost (Columnar Compression)
```
7 years of transaction data (1B records/year):

Row-oriented Parquet:
├── Uncompressed: 350GB (50 bytes per record)
├── With compression: 140GB
└── S3 cost: $0.023/GB/month = $3.22K/month

Iceberg (columnar):
├── Uncompressed: 150GB (smaller due to column ordering)
├── With compression: 100GB (better compression per column)
└── S3 cost: $0.023/GB/month = $2.30K/month

**Savings**: ~$1K/month per domain, $5K/month company-wide
**Over 7 years**: $420K savings for transactions domain alone
```

### Time-Travel for Compliance
```sql
-- Auditors need to reconstruct state from specific date
SELECT * FROM transactions.raw_transactions
  FOR SYSTEM_TIME AS OF '2026-04-25 10:00:00'
WHERE transaction_id = '12345';

-- Result: Data as it existed on that date (immutable snapshots)
-- Use case: SAR (Suspicious Activity Report) investigations
```

---

## Consequences

### Positive
- ✅ Schema evolution is effortless (key for domain ownership)
- ✅ ACID transactions prevent data corruption
- ✅ Time-travel enables compliance audits
- ✅ Cost-optimized (columnar compression + partition pruning)
- ✅ Open format (not proprietary like Delta)

### Negative (Trade-offs)
- ❌ Operational complexity (metadata management)
- ❌ Learning curve (Iceberg concepts like manifests)
- ❌ Snapshot compaction needed (prevent metadata explosion)
- ❌ Ecosystem smaller than Parquet (tooling less mature)

---

## Alternatives Considered

### Alternative 1: Parquet + Hive Metastore (Legacy)
**Pros**: Mature, simple
**Cons**: 
- Schema changes require full rewrite (defeats domain ownership)
- No ACID (duplicates possible)
- No time-travel (compliance risk)
- **Rejected**: Doesn't support schema evolution requirement

### Alternative 2: Delta Lake (Databricks)
**Pros**: ACID, time-travel, widely used
**Cons**:
- Proprietary (Databricks owns development)
- Open source exists but not fully compatible
- Lock-in risk
- **Rejected**: Want open format; Apache Iceberg is pure OSS

### Alternative 3: Apache Hudi
**Pros**: COW (Copy-on-Write) incremental writes, schema evolution
**Cons**:
- Smaller ecosystem than Iceberg
- Query performance slower on large scans
- Learning curve higher
- **Considered but rejected**: Iceberg better for fintech use case

### Alternative 4: Star Schema (Snowflake/BigQuery)
**Pros**: Fully managed, no ops
**Cons**:
- Vendor lock-in (not open source)
- Cost at scale (fintech data volume = $$$)
- Schema not flexible (dimensional modeling rigid)
- **Rejected**: Need open format; avoid vendor lock-in

---

## Implementation Details

### Iceberg Table Initialization
```python
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, StringType, DoubleType, LongType

catalog = load_catalog("rest")
schema = Schema(
    NestedField(1, "transaction_id", StringType(), required=True),
    NestedField(2, "account_id", StringType(), required=True),
    NestedField(3, "amount", DoubleType(), required=True),
    NestedField(4, "timestamp", LongType(), required=True),
)

table = catalog.create_table(
    "transactions.raw_transactions",
    schema=schema,
    partitions=[("year", "year"), ("month", "month"), ("day", "day")],
)
```

### Adding a Column (Schema Evolution)
```python
# No rewrite needed!
table.update_schema() \
    .add_column("fraud_risk_score", DoubleType(), doc="ML fraud model output") \
    .commit()

# Spark automatically handles NULL for old data:
spark.sql("""
  SELECT transaction_id, fraud_risk_score
  FROM transactions.raw_transactions;
""")
# Result: new data has score; old data has NULL
```

---

## Monitoring

**Iceberg-specific metrics**:
```yaml
metrics:
  - iceberg_snapshot_count{table}  # Number of snapshots (compact if > 100)
  - iceberg_manifest_files{table}  # Metadata file count
  - iceberg_metadata_size_mb{table}  # Metadata overhead
  - iceberg_partition_count{table}  # Number of partitions
  - iceberg_data_file_count{table}  # Number of data files per partition

alerts:
  - snapshots > 100: Run compaction job
  - metadata_size > 10GB: Investigate snapshot history
  - data_files > 1000 per partition: Run file compaction
```

---

## Success Criteria

- ✅ Schema updates complete in < 5 minutes (vs. 8 hours for Parquet)
- ✅ Zero duplicate records ingested (exactly-once semantics)
- ✅ Time-travel queries work for audit trails
- ✅ Cost stays < $2.5K/month for 7-year retention

---

## References

- Apache Iceberg: https://iceberg.apache.org/
- Iceberg Spec: https://iceberg.apache.org/spec/
- Iceberg vs Delta: https://iceberg.apache.org/faq/

---

## Sign-Off

| Role | Name | Date | Status |
|------|------|------|--------|
| Platform Lead | - | 2026-04-05 | Approved |
| Storage Architect | - | 2026-04-05 | Approved |
