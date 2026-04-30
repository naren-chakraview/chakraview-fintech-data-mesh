# Fintech Data Mesh with Apache Iceberg: Design Specification

**Date:** 2026-04-30  
**Project:** chakraview-fintech-data-mesh  
**Status:** Design Review  
**Audience:** Data Engineers, Architects, Compliance/Risk Teams

---

## Executive Summary

This project is a production-grade reference implementation of a **data mesh architecture** using **Apache Iceberg** as the unified lakehouse, demonstrating:

- **Decentralized domain ownership** (Transactions, Accounts, Risk/Compliance, Counterparties, Market Data) with autonomous schema and data product management
- **Unified analytical engine** (Apache Spark SQL) enabling cross-domain queries without breaking domain boundaries
- **Data products as first-class citizens** — formal SLAs, governance, and self-service discoverability
- **Federated governance** — each domain owns their data products' lifecycle; approval workflows are automated where safe, domain-owner-approved where required
- **Real-time + analytical duality** — Kafka for hot-path consumers (<100ms), Iceberg for cold-path analytics (<1 hour)
- **Enterprise production guidance** — architectural trade-offs, scaling strategies, compliance controls for large fintech organizations

The reference implementation is a **hybrid monorepo** where domains are independent subdirectories but can be demonstrated, tested, and deployed as a cohesive system.

---

## 1. Architecture Overview

### 1.1 Core Components

**Storage Layer:**
- Apache Iceberg as the primary data lake (columnar Parquet format)
- Single shared catalog (Iceberg REST Catalog recommended; Nessie for schema versioning optional)
- S3-compatible object storage (S3, GCS, Azure Blob) for table data and manifest files

**Compute/Query Layer:**
- Apache Spark SQL as the unified analytical query engine
- Spark Structured Streaming for real-time ingestion (Kafka → Iceberg micro-batches, 5-10 min interval)
- Presto/Trino as documented alternative for interactive analytics

**Data Exchange:**
- Apache Kafka for event streaming (each domain publishes events to its topic)
- Schema Registry (Confluent) for schema versioning and validation

**Metadata & Discovery:**
- Iceberg REST Catalog (stateless, cloud-native)
- Data Product Registry (YAML files in Git, auto-enriched with Iceberg/Spline metadata)
- Spline or OpenLineage for automatic lineage capture from Spark jobs

**Governance & Access:**
- OPA (Open Policy Agent) for ABAC policies
- Self-service portal (FastAPI + React) for discovery and access requests
- Approval workflow engine (integrates with Slack/email)

**Observability:**
- Prometheus for metrics (freshness, quality scores, query performance)
- Grafana for dashboards (data product health, domain metrics)
- Great Expectations for data quality testing
- Elasticsearch or S3 for immutable audit logs

### 1.2 Five Fintech Domains

Each domain owns a subdirectory in the monorepo and is responsible for ingest, schema evolution, and data product definitions.

| Domain | Responsibility | Key Tables | Freshness SLA | Consistency Model |
|--------|---|---|---|---|
| **Transactions** | Payment events, settlement records, messaging | `raw_transactions`, `settlement_status`, `clearing_log` | 5 min | Append-only; idempotent via Kafka dedup |
| **Accounts** | Customer accounts, hierarchies, balances | `accounts`, `account_balances`, `account_limits` | 10 min | Strong consistency (daily snapshot) |
| **Risk & Compliance** | KYC/AML verdicts, fraud scores, audit events | `kyc_verdicts`, `fraud_scores`, `sanctions_matches`, `audit_log` | 10 min | Strong consistency; immutable audit log |
| **Counterparties** | Merchants, banks, brokers; master data | `merchants`, `bank_relationships`, `credit_limits` | 1 hour | Slow-moving; reference data |
| **Market Data** | FX rates, bond prices, indices | `fx_rates`, `bond_prices`, `equity_indices` | Real-time (Kafka) | External feed; eventual consistency |

---

## 2. Data Flow Architecture

### 2.1 Ingest Pipeline

**Per-Domain Pattern:**

```
[External Source / Event]
    ↓
[Kafka Topic: domain-events]
    ↓
[Spark Structured Streaming Job]
    ├─ Schema validation (against Schema Registry)
    ├─ Deduplication (Kafka offset tracking)
    ├─ Error handling (DLQ for malformed events)
    ↓
[Iceberg Append (5-10 min micro-batch)]
    ↓
[Periodic Compaction (daily)]
```

**Key Mechanism:**
- Spark Structured Streaming with `checkpointLocation` for exactly-once semantics
- Iceberg hidden column `__file_path` + `__pos` for deduplication
- Batch writes every 5-10 minutes to balance write efficiency vs freshness
- Compaction job (triggered daily or on-demand) merges small files, removes delete files

**Example: Transactions Domain Ingest**
```
Transactions Kafka Topic (partitioned by account_id)
  ↓ [Spark consumer, 5 min batches]
  ↓ Validates against Avro schema (v2.1 from Schema Registry)
  ↓ Deduplicates using Kafka offset (idempotent)
  ↓ Appends to transactions.raw_transactions (Iceberg table)
  ↓ Compaction job (daily): merge small files, compress
```

### 2.2 Analytical Query Path

**Cross-Domain Queries:**

```
Analyst / BI Tool
    ↓
[Spark SQL Query]
    ↓ Reads Iceberg snapshots
    ├─ transactions.raw_transactions (latest snapshot)
    ├─ accounts.account_balances (latest snapshot)
    ├─ risk_compliance.fraud_scores (latest snapshot)
    ↓ Evaluates at query time (no materialized views required, but optional)
    ↓
[Results returned, logged to audit trail]
```

**Consistency Model:**
- Iceberg snapshots are **eventual consistency** — queries read the latest snapshot at query time
- Typical freshness: **<1 hour** (5-10 min ingest + 10-50 min query latency)
- Time-travel supported: `SELECT * FROM table TIMESTAMP AS OF '2026-04-30 14:30:00'`

### 2.3 Real-Time vs Analytical Tension

**Real-time consumers** (fraud detection, settlement engines):
- Read directly from Kafka topics (Transactions, Risk)
- Latency: <100ms
- Consistency: strong (reading source of truth)

**Analytical consumers** (compliance reports, dashboards):
- Read from Iceberg (eventual consistency)
- Latency: <1 hour
- Consistency: eventual
- Trade-off: simpler infrastructure, lower cost, acceptable for regulatory reports (most regulations allow 1-day freshness)

**Design Decision:** Domains explicitly document per use case whether to consume from Kafka (hot) or Iceberg (cold). Not all data needs to be both; transactions might be hot-path only, while historical risk models are cold-path only.

### 2.4 Metadata & Lineage Capture

**Metadata Attached to Every Iceberg Write:**
```json
{
  "write_timestamp": "2026-04-30T14:15:30Z",
  "source_kafka_topic": "transactions-raw",
  "kafka_offset_range": "1000-1500",
  "schema_version": "2.1",
  "ingest_job_id": "spark-job-20260430-141530",
  "record_count": 5000,
  "checksum": "abc123..."
}
```

**Lineage Capture:**
- Spline agent integrated into Spark jobs → captures transformations
- OpenLineage compatible → enables federation with other data platforms
- Audit log stores: user, query, data products accessed, timestamp, rows returned

**Compliance Use Case:**
- Query: "Show me all data accessed between 2026-04-29 10:00 and 14:00"
- Result: all queries + data lineage for audit trails, regulatory submissions

---

## 3. Data Products: First-Class Citizens

### 3.1 What is a Data Product?

A **data product** is a curated, documented, discoverable analytical asset published by a domain with:
- **Definition:** One or more Iceberg tables + schema
- **Owner:** Domain team responsible for SLAs
- **SLA:** Freshness, availability, completeness guarantees
- **Access Policy:** Who can read/write, approval requirements
- **Documentation:** What this is for, use cases, example queries
- **Observability:** Real-time health metrics (freshness, quality, usage)
- **Lineage:** Upstream sources + downstream consumers

### 3.2 Data Product Definition (YAML)

**File Location:** `domains/{domain}/data-products/{product_name}.yaml`

**Example: transactions/data-products/transaction-feed.yaml**

```yaml
---
name: transaction-feed
version: "1.0"
owner: transactions-domain
owner_email: transactions@chakra.fintech
domain: transactions

description: |
  Real-time transaction feed for all payment and settlement events.
  Includes T+0 settlement tracking, reversals, and clearing status.
  Used for fraud detection, settlement reconciliation, and regulatory reporting.

tables:
  - name: raw_transactions
    iceberg_table: transactions.raw_transactions
    schema_version: "2.1"
    partitions: [year, month, day, account_id]
    doc: "Raw transaction events as received from core banking system"
  
  - name: settlement_status
    iceberg_table: transactions.settlement_status
    schema_version: "1.0"
    partitions: [year, month, day]
    doc: "Settlement status per transaction (pending, cleared, failed)"

sla:
  freshness:
    value: 5
    unit: minutes
    measured_as: "max(current_time - kafka_ingest_timestamp)"
  
  availability:
    value: 99.9
    unit: percent
    measured_as: "successful_queries / total_queries"
  
  completeness:
    value: 100
    unit: percent
    measured_as: "row count matches banking system +/- 10 within 10 min"

access_policy:
  default: deny
  approval_required: true
  approval_sla_hours: 4  # business hours
  self_approve_roles: [internal-fraud-team, settlements-ops]
  columns:
    - name: account_id
      classification: confidential
      masked_for_roles: [external-analysts]
    - name: amount
      classification: sensitive
    - name: merchant_category_code
      classification: public

tags: [real-time, settlement-critical, pci-dss, sox-relevant]
use_cases:
  - fraud_detection_real_time
  - settlement_reconciliation
  - regulatory_reporting_daily
  - compliance_audits

upstream_lineage:
  - kafka.transactions-raw (external system: core banking)
  - kafka.settlement-messages (external system: clearing house)

downstream_lineage:
  - risk_compliance.fraud-scores (consumes raw_transactions)
  - accounts.account-balance-materialized (uses settlement_status)

quality_rules:
  - rule: "amount > 0"
    description: "All transaction amounts must be positive"
  - rule: "booking_date <= settlement_date"
    description: "Settlement cannot precede booking"
  - rule: "null_count(account_id) == 0"
    description: "No missing account IDs"

retention_policy:
  value: 7
  unit: years
  rationale: "Regulatory requirement for transaction audit trail"
```

### 3.3 Data Product Registry

- **Registry:** YAML files + Git versioning (can be auto-enriched from Iceberg catalog)
- **Discovery:** Indexed in self-service portal; searchable by name, owner, tags, use case
- **Versioning:** Product definition versions tracked in Git; breaking changes trigger impact analysis
- **Governance:** Each data product is a contract — owners pledge to maintain SLAs, document changes, manage access

---

## 4. Federated Governance & Self-Service Access

### 4.1 Governance Model

**Principle:** Data products are owned by domains; governance decisions are made at the domain level with platform-wide policy enforcement.

**Who Does What:**

| Actor | Responsibility |
|-------|---|
| **Domain Owner** | Define SLA, approve access requests, manage schema evolution, monitor quality |
| **Data Owner** (within domain) | Ensure data quality, document lineage, maintain data product YAML |
| **Platform Team** | Provide tools (catalog, OPA, approval workflow), enforce compliance rules (retention, masking, audit) |
| **Consumer** | Request access, adhere to SLA/retention policies, report data quality issues |

### 4.2 Self-Service Access Portal

**Technology:** FastAPI backend + React frontend, deployed alongside catalog

**Workflow:**

```
1. DISCOVERY
   ├─ User searches: "transaction" → finds transaction-feed data product
   ├─ Views: owner, SLA, schema, example queries, health metrics (freshness, quality)
   └─ Can see: downstream consumers, upstream sources, usage statistics

2. REQUEST
   ├─ User clicks "Request Access"
   ├─ System shows: data classification, retention policy, cost estimate
   ├─ User provides: justification (use case), requested permissions (read/write), time limit (if temporary)
   └─ System calculates: risk score (data sensitivity × user role)

3. APPROVAL
   ├─ Low-risk requests (read-only, non-PII, internal user):
   │  └─ OPA auto-approves; user gets Spark credentials within 5 min
   ├─ Medium-risk requests:
   │  └─ Domain owner gets Slack notification, can approve in portal or via reaction
   ├─ High-risk requests (PII, write access, external user):
   │  └─ Requires multi-layer approval (domain owner + compliance)
   └─ SLA: 4 hours for domain owner approval

4. PROVISIONING
   ├─ System generates: Iceberg catalog token (time-limited)
   ├─ Provides: SQL snippets to query the product (with masking applied)
   ├─ Records: approval decision in audit log
   └─ Notifies user + domain owner via Slack

5. USAGE TRACKING
   ├─ Every query logged: user, data product, query hash, rows accessed, cost
   ├─ Domain owner dashboard: usage by data product, top consumers
   ├─ Cost chargeback (optional): cost/month per consumer
   └─ Revocation: can revoke access in portal; effective immediately
```

### 4.3 Access Control: OPA Policies

**ABAC (Attribute-Based Access Control)** implemented in OPA Rego:

```rego
# Example: Allow read-only access if approved and non-sensitive data
allow_read {
    input.action == "read"
    input.data_product == "transaction-feed"
    input.user_role in ["internal-analyst", "fraud-team"]
    input.approval_status == "approved"
    input.target_columns not in ["account_holder_name", "ssn"]
}

# Auto-approve low-risk read access
auto_approve {
    input.action == "read"
    input.data_product == "transaction-feed"
    input.user_role in ["internal-analyst"]
    input.target_columns in ["amount", "merchant_id", "timestamp"]
}
```

**Approval SLAs:**
- Auto-approve: read-only, non-sensitive, internal user → 5 min
- Domain owner approval: write, PII access, external user → 4 hours (business)
- Multi-approval: sensitive + regulatory data → 24 hours

---

## 5. Project Structure: Hybrid Monorepo

### 5.1 Directory Layout

```
chakraview-fintech-data-mesh/
├── README.md
├── CLAUDE.md (internal instructions)
├── .gitignore
│
├── docs/
│   ├── architecture/
│   │   ├── 00-overview.md
│   │   ├── data-mesh-principles.md
│   │   ├── iceberg-design-decisions.md
│   │   ├── real-time-vs-analytics.md
│   │   ├── data-products.md
│   │   └── federated-governance.md
│   │
│   ├── domains/
│   │   ├── transactions/
│   │   │   ├── schema.md (table definitions)
│   │   │   ├── data-products.md (product SLAs, access policies)
│   │   │   ├── use-cases.md (fraud, settlement, reporting)
│   │   │   └── examples.md (SQL queries, Spark patterns)
│   │   ├── accounts/
│   │   ├── risk-compliance/
│   │   ├── counterparties/
│   │   └── market-data/
│   │
│   ├── platform/
│   │   ├── discovery.md (self-service portal architecture)
│   │   ├── observability.md (health monitoring, metrics)
│   │   ├── governance-policies.md (OPA rules, approval workflows)
│   │   └── lineage.md (Spline integration, impact analysis)
│   │
│   ├── production-guide/
│   │   ├── 01-deployment.md (K8s, Helm, cloud setup)
│   │   ├── 02-schema-evolution.md (versioning, breaking changes)
│   │   ├── 03-scaling-strategies.md (file sizes, partitioning, compaction)
│   │   ├── 04-compliance-controls.md (retention, masking, audit)
│   │   ├── 05-troubleshooting.md (slow queries, data quality issues)
│   │   └── 06-architectural-trade-offs.md (detailed decision matrix)
│   │
│   └── superpowers/specs/
│       └── 2026-04-30-fintech-data-mesh-design.md (this file)
│
├── domains/
│   ├── transactions/
│   │   ├── data-products/
│   │   │   ├── transaction-feed.yaml
│   │   │   ├── settlement-view.yaml
│   │   │   └── clearing-status.yaml
│   │   │
│   │   ├── ingest/
│   │   │   ├── requirements.txt
│   │   │   ├── ingest_job.py (Spark Structured Streaming consumer)
│   │   │   ├── schemas.py (table schemas, Iceberg definitions)
│   │   │   └── tests/
│   │   │       ├── test_schema_validation.py
│   │   │       └── test_ingest_idempotency.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── avro/
│   │   │   │   └── transaction-v2.1.avsc (Kafka schema)
│   │   │   └── iceberg/
│   │   │       ├── raw_transactions.schema
│   │   │       └── settlement_status.schema
│   │   │
│   │   ├── queries/
│   │   │   ├── transaction-by-account.sql
│   │   │   ├── settlement-reconciliation.sql
│   │   │   └── time-travel-audit.sql
│   │   │
│   │   └── README.md (domain-specific documentation)
│   │
│   ├── accounts/
│   │   ├── data-products/ (account, account_balances)
│   │   ├── ingest/
│   │   ├── schemas/
│   │   ├── queries/
│   │   └── README.md
│   │
│   ├── risk-compliance/
│   ├── counterparties/
│   └── market-data/
│
├── platform/
│   ├── catalog/
│   │   ├── docker-compose.yml (Iceberg REST catalog + PostgreSQL)
│   │   ├── catalog-config.yaml
│   │   └── nessie-config.yaml (optional)
│   │
│   ├── discovery/
│   │   ├── backend/
│   │   │   ├── main.py (FastAPI app)
│   │   │   ├── models.py (DataProduct, AccessRequest schemas)
│   │   │   ├── routes/ (search, request, approval)
│   │   │   ├── opa_client.py (OPA policy evaluation)
│   │   │   └── tests/
│   │   └── frontend/
│   │       ├── src/
│   │       │   ├── pages/
│   │       │   │   ├── ProductSearch.tsx
│   │       │   │   ├── AccessRequest.tsx
│   │       │   │   └── Dashboard.tsx
│   │       │   └── components/
│   │       └── package.json
│   │
│   ├── governance/
│   │   ├── opa-policies/
│   │   │   ├── abac.rego (attribute-based access control)
│   │   │   ├── compliance.rego (retention, masking rules)
│   │   │   └── audit.rego (query logging, change tracking)
│   │   │
│   │   ├── approval-workflows/
│   │   │   ├── auto_approve.py (low-risk auto-approval)
│   │   │   ├── slack_integration.py (notifications + reactions)
│   │   │   └── workflow_state_machine.py
│   │   │
│   │   └── tests/
│   │
│   ├── observability/
│   │   ├── metrics/
│   │   │   ├── freshness_checks.py (Prometheus metrics)
│   │   │   ├── quality_checks.py (Great Expectations integration)
│   │   │   └── cost_tracking.py
│   │   │
│   │   ├── dashboards/
│   │   │   ├── data-product-health.json (Grafana)
│   │   │   ├── domain-metrics.json
│   │   │   └── compliance-audit.json
│   │   │
│   │   └── audit/
│   │       ├── query_logger.py (log every query to Elasticsearch)
│   │       └── lineage_enricher.py (add lineage context to logs)
│   │
│   ├── lineage/
│   │   ├── spline_integration.py (auto-capture Spark lineage)
│   │   ├── impact_analyzer.py (schema change → downstream impact)
│   │   └── lineage_api.py (expose lineage via REST API)
│   │
│   └── docker-compose.yml (complete platform: catalog, governance, observability, lineage)
│
├── shared/
│   ├── schemas/
│   │   ├── avro/ (shared Avro types)
│   │   └── protobuf/ (alternative schema format)
│   │
│   ├── utils/
│   │   ├── iceberg_helpers.py (table creation, partition helpers)
│   │   ├── logging.py (structured logging, compliance context)
│   │   ├── metrics.py (Prometheus instrumentation)
│   │   └── audit.py (audit event tracking)
│   │
│   ├── compliance/
│   │   ├── masking_rules.py (PII column masking)
│   │   ├── retention_policy.py (auto-delete aged data)
│   │   └── lineage_validator.py (ensure lineage completeness)
│   │
│   └── tests/ (shared test fixtures, utilities)
│
├── tests/
│   ├── integration/
│   │   ├── test_cross_domain_queries.py (fraud score + transaction + account join)
│   │   ├── test_data_quality.py (Great Expectations)
│   │   └── test_lineage_completeness.py (Spline validation)
│   │
│   ├── compliance/
│   │   ├── test_audit_logging.py (all queries logged)
│   │   ├── test_pii_masking.py (sensitive columns masked)
│   │   ├── test_retention_enforcement.py (data deleted after N days)
│   │   └── test_access_control.py (OPA policies enforced)
│   │
│   └── performance/
│       ├── test_query_performance.py (benchmark queries)
│       └── test_compaction_impact.py (file size → query speed)
│
├── mkdocs.yml
├── requirements.txt (Python: Spark, Iceberg, Kafka, Pydantic, etc.)
└── docker-compose.yml (entire local environment: Kafka, Spark, catalog, governance, observability)
```

### 5.2 Implementation Patterns

**Domain Ingest Job (transactions/ingest/ingest_job.py):**
```python
# Spark Structured Streaming consuming Kafka, validating, writing Iceberg
# Schema validation against Registry, deduplication, error handling
# Checkpointing for exactly-once semantics, metadata logging
```

**Data Product YAML:** Each domain publishes 1-3 YAML files (transaction-feed, settlement-view, etc.)

**Query Examples:** SQL + Spark patterns in each domain directory

**Compliance Helpers:** Shared Python utilities for masking, retention, lineage

**Tests:** Unit (schema validation), integration (cross-domain queries), compliance (audit, masking, retention)

---

## 6. Production Guidance: Architectural Trade-Offs

### 6.1 Decision Matrix

| Decision | Option A | Option B | Option C | Recommendation |
|----------|----------|----------|----------|---|
| **Catalog Backend** | Iceberg REST (stateless, cloud-native) | Nessie (Git-like versioning) | Unity Catalog (Databricks) | **Option A** for portability; Option B if versioning is critical |
| **Storage Layer** | S3/Cloud (cheap, async) | HDFS/NAS (fast, consistent) | — | **Option A** for fintech scale |
| **Query Engine** | Spark SQL (batch + streaming) | Presto/Trino (interactive) | DuckDB (local) | **Option A** as primary; Option B for BI dashboards |
| **Real-Time Ingest** | 5-10 min batches (recommended) | 1 min batches (fresher) | Streaming inserts (experimental) | **Option A** for most use cases; Option B if <2 min freshness required |
| **Schema Evolution** | Schema Registry + Avro (strict) | Flexible JSON (loose) | — | **Option A** for compliance |
| **Data Product Definition** | Lightweight YAML (recommended) | Heavyweight metadata platform | Hybrid (YAML + auto-enrichment) | **Option C** (best of both) |
| **Access Control** | OPA + ABAC (flexible, auditable) | RBAC (simple) | Trust-on-first-use | **Option A** for regulated industries |
| **Approval SLA** | 4 hours (balanced) | Immediate (fast) | 24+ hours (strict) | **Option A** for fintech |
| **Observability Scope** | Full stack (comprehensive) | Freshness + quality only | MVP → expand | **Option A** for production; Option C for v1 MVP |

### 6.2 Scaling Considerations

**File Size & Partitioning:**
- Iceberg recommends files **128MB-1GB** per partition
- Transactions domain (high volume): partition by `[year, month, day, account_id]` → ~1M rows/file
- Compaction frequency: daily (balances write efficiency vs metadata churn)

**Catalog Load:**
- Iceberg REST catalog can handle 10M+ tables; metadata operations scale to 1000s of concurrent queries
- If hitting limits: Nessie (distributed) or Federation (separate catalogs per domain)

**Query Performance:**
- Column pruning + partition elimination critical
- Time-travel queries slower (reads multiple snapshots); use for audits, not operational queries
- Denormalized views/materializations optional for common joins (e.g., `account_with_fraud_score`)

---

## 7. Key Implementation Concerns

### 7.1 Real-Time Consistency & Exactly-Once Semantics

**Challenge:** Kafka offset tracking + Iceberg write atomicity

**Solution:**
- Spark Structured Streaming with `checkpointLocation` → exactly-once semantics
- Iceberg deduplication via hidden `__file_path` + `__pos` columns
- Idempotent writes (retry on failure does not duplicate)

### 7.2 Cross-Domain Data Governance

**Challenge:** Decentralized ownership but unified analytics

**Solution:**
- Clear data product contracts (SLAs, schema versioning)
- Impact analysis tool: schema change → downstream consumers notified
- Approval workflows: breaking changes require downstream domain sign-off

### 7.3 Compliance & Audit Trails

**Challenge:** Fintech regulations require immutable, complete audit logs

**Solution:**
- Every query logged (Spark event logs → Elasticsearch or S3)
- Lineage capture (Spline) → can answer "where did this data come from?"
- Retention policies enforced (auto-delete after N years)
- PII masking at query time (OPA policies)

### 7.4 Cost Control

**Challenge:** Large-scale lake queries can be expensive (bytes scanned, compute)

**Solution:**
- Partition pruning documentation (guide teams to efficient queries)
- Cost dashboard: bytes ingested/queried per domain
- Optional: cost chargeback model (charge domain for their query volume)

---

## 8. Testing Strategy

**Unit Tests:**
- Domain ingest jobs: schema validation, deduplication logic
- Governance policies: OPA rules with example inputs

**Integration Tests:**
- Cross-domain queries (fraud detection pulling from Transactions + Risk + Accounts)
- End-to-end: Kafka → Iceberg → query → audit log

**Compliance Tests:**
- Lineage completeness: all Spark jobs captured by Spline
- Audit logging: all queries logged with user/timestamp/data product
- PII masking: sensitive columns masked for unauthorized users
- Retention: data deleted after N days per classification

**Performance Tests:**
- Query benchmarks (time-travel vs current snapshot)
- Compaction impact (file count/size → query speed)
- Catalog load (1000s of concurrent queries)

---

## 9. Deployment

### 9.1 Local Development (Docker Compose)

```yaml
# Single docker-compose.yml with all services:
# - Kafka (transactions-raw, accounts, etc. topics)
# - Spark (with Iceberg support)
# - Iceberg REST Catalog + PostgreSQL
# - Schema Registry
# - OPA for policies
# - FastAPI discovery portal
# - Prometheus + Grafana
# - Elasticsearch for audit logs
# - Spline for lineage
```

### 9.2 Cloud Deployment (Kubernetes)

**Helm Charts:**
- Per-domain ingest job (CronJob for daily compaction, Deployment for streaming)
- Catalog (Deployment + StatefulSet for backing store)
- Governance service (API, approval workflows)
- Observability (Prometheus, Grafana as Deployments)

**Cloud Storage:** S3/GCS for table data + manifests

**Configuration:** Helm values for namespace, storage paths, catalog endpoints

---

## 10. Success Criteria & Validation

**Technical:**
- ✅ Five domains with independent ingest pipelines, real-time + batch freshness SLAs met
- ✅ Cross-domain queries execute correctly (fraud scoring using 3+ domains)
- ✅ Lineage captured automatically for all Spark jobs
- ✅ Time-travel queries work (can reproduce historical snapshots for audits)
- ✅ Self-service portal finds data products, approval workflows execute

**Operational:**
- ✅ Schema evolution process documented and tested (add/drop columns, type changes)
- ✅ Compaction job reduces file count without breaking queries
- ✅ Data quality tests detect missing/invalid data
- ✅ Audit logs complete (every query logged with user/timestamp/lineage)

**Compliance:**
- ✅ PII columns masked for unauthorized users
- ✅ Retention policies enforced (aged data deleted)
- ✅ Access approval SLAs met (4 hours for domain approval)
- ✅ Compliance audit: can trace any data point back to source (lineage) and answer who accessed it (audit log)

---

## 11. Future Evolution (Out of Scope)

- **Federation:** Support multiple Iceberg instances (domain-specific catalogs) with federated query engine
- **Event Sourcing:** Kafka as immutable event log, Iceberg as materialized views
- **Streaming Analytics:** Spark Streaming → materialized tables for real-time BI
- **Data Contracts:** Formalize schema contracts between producers/consumers
- **ML Pipelines:** Feature store integration for ML workloads

---

## Appendix: Technology Stack Summary

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Data Lake | Apache Iceberg | Columnar, schema evolution, time-travel, ACID |
| Storage | S3 / GCS / Azure Blob | Cloud-native, cost-effective, multi-region |
| Ingest | Kafka + Spark Structured Streaming | Real-time events + batch micro-batches |
| Query | Spark SQL (primary), Presto (alternative) | Complex joins, ML integration |
| Catalog | Iceberg REST Catalog | Stateless, cloud-native |
| Schema Registry | Confluent Schema Registry | Schema versioning, validation |
| Lineage | Spline + OpenLineage | Automatic capture, compliance audits |
| Governance | OPA (Open Policy Agent) | Flexible, code-as-policy, no vendor lock-in |
| Discovery | FastAPI + React | Custom portal, tight integration with policies |
| Metrics | Prometheus + Grafana | Standard observability stack |
| Quality | Great Expectations | Data quality testing, documentation |
| Audit Log | Elasticsearch / S3 | Immutable, queryable logs |

---

## Document History

| Date | Version | Changes |
|------|---------|---------|
| 2026-04-30 | 1.0 | Initial design spec |

