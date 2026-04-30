# Data Mesh Principles

The data mesh pattern rests on four core principles. This implementation demonstrates each in the fintech context.

---

## 1. Domain Ownership (Decentralized)

### Definition
Each domain team *owns* its data end-to-end: schema definition, ingest pipeline, SLAs, quality rules, governance policies, and observability.

### In This Implementation
- **Transactions Domain** owns `transactions.raw_transactions` and `transactions.settlement_status` tables
  - Defines schema in Avro (v2.1, with historical versions)
  - Implements ingest job (Spark Structured Streaming)
  - Sets SLAs (5-minute freshness, 99.9% availability)
  - Enforces retention (7 years per SOX requirement)
  - Publishes data product YAML with quality rules

- **Risk/Compliance Domain** owns fraud scores, KYC verdicts, sanctions lists
  - Defines 10-year retention (AML requirement)
  - Manages masking policies (PII columns hidden from external analysts)
  - Publishes approval workflows for sensitive columns
  - Owns audit trail (all queries logged)

### Benefits
- **Speed**: No central ETL team bottleneck; domains iterate on their schema independently
- **Compliance**: Policies match domain requirements (risk data ≠ marketing data)
- **Cost control**: Each domain optimizes its own partitioning, retention, quality checks
- **Accountability**: Domain owns freshness SLA; domain on-call if data is stale

### Anti-Pattern: Everything Approved Centrally
Avoid: "All schema changes must be reviewed by the Platform team."
This reintroduces the waterfall bottleneck data mesh eliminates. Instead, enforce policy (via OPA) but allow autonomous schema evolution.

---

## 2. Federated Governance (Not Centralized)

### Definition
Instead of a centralized approval board, *policies encoded as code* (OPA) enforce compliance rules. Governance is federated: many domains, one set of policies.

### In This Implementation

**OPA Policies** replace manual review:

```rego
# From platform/governance/opa-policies/abac.rego

# Default deny (zero-trust)
default allow = false

# Auto-approve for read-only analysts
allow {
  input.action == "read"
  input.user_role == "analyst"
  input.data_classification != "restricted"
}

# Require approval for sensitive data modifications
deny {
  input.action == "write"
  input.data_classification == "pii"
}

# Apply masking automatically
apply_masking {
  input.user_role == "external_analyst"
  input.column_classification == "pii"
}
```

**Example Decision Flow**:
```
User: "Can I query risk_compliance.fraud_scores?"

OPA Evaluation:
├── User role: external_analyst
├── Data classification: pii (fraud_score is internal)
├── Action: read
├── Result: DENY (external analyst + restricted data)

User: "Can I query transactions.merchant_id?"

OPA Evaluation:
├── User role: external_analyst
├── Data classification: pii
├── Action: read
├── Masking rule applies: Show partial (first 4 chars)
├── Audit: Log access
├── Result: ALLOW with masking
```

### Benefits
- **Testable**: OPA policies are code; run unit tests on policy logic
- **Versionable**: Policies in git, change history tracked
- **Scalable**: Add new domains without changing policies; enforce via attributes, not roles
- **Decoupled**: Application code doesn't embed compliance rules

### Anti-Pattern: Role-Based Access
Avoid: "risk_analyst role has access to fraud_scores"
This breaks when you add new data types or new roles. Instead use attributes:
```rego
allow {
  input.user_role == "risk_analyst"
  input.data_classification == "high_sensitivity"  # Attribute-based
}
```

---

## 3. Data Product as First-Class Citizen

### Definition
Data is not just tables; it's a *product* with a formal contract. The contract specifies:
- Schema and versioning
- SLAs (freshness, availability, completeness)
- Quality rules (what makes data trustworthy)
- Access policies (who can see what)
- Retention and compliance requirements

### In This Implementation

**Data Product Specification** (YAML):

```yaml
---
name: transaction-feed
version: "1.0"
domain: transactions
owner: transactions-domain
owner_email: transactions@chakra.fintech

description: |
  Real-time transaction events with settlement status.
  Consumed by: fraud-detection, account-reconciliation, 
  analytics (revenue, compliance reporting)

tables:
  - name: raw_transactions
    iceberg_table: transactions.raw_transactions
    schema_version: "2.1"
    doc: "Raw transaction events with all fields"
    partitions: [year, month, day, account_id]

sla:
  freshness:
    value: 5
    unit: minutes
  availability:
    value: 99.9
    unit: percent
  completeness:
    value: 99
    unit: percent

quality_rules:
  - name: positive_amount
    rule: "amount > 0"
    impact: critical
  - name: valid_settlement
    rule: "booking_date <= settlement_date"
    impact: high
  - name: reasonable_delay
    rule: "settlement_timestamp - booking_timestamp <= 3 days"
    impact: medium

access_policy:
  default: deny
  approval_required: false
  columns:
    - name: account_id
      classification: pii
      masked_for_roles: [external_analyst, contractor]
    - name: account_holder_name
      classification: pii
      masked_for_roles: [external_analyst]
    - name: card_number
      classification: pci
      masked_for_roles: [everyone_except_payments]

retention_policy:
  value: 7
  unit: years
  reason: "SOX compliance requirement"
```

### Discovery and Self-Service
Consumers find products via portal:
```bash
# Find what data is available
curl http://localhost:8000/api/products?query=fraud

# Response includes SLA, masking, quality, retention upfront
{
  "name": "fraud-scoring",
  "domain": "risk_compliance",
  "freshness_sla": "10 minutes",
  "availability_sla": "99.99%",
  "quality_rules": 5,
  "retention": "10 years",
  "masking": ["account_id", "ssn"]
}

# Request access
curl -X POST http://localhost:8000/api/access-requests \
  -d '{
    "user_id": "analyst_42",
    "data_product_id": "fraud-scoring",
    "justification": "Weekly fraud analysis for risk committee"
  }'
```

### Benefits
- **Trust**: Consumers know freshness, quality, retention before using data
- **SLA enforcement**: Platform can alert if freshness > SLA (e.g., data stale > 5 min)
- **Governance clarity**: Masking policies and approval workflows explicit
- **Scaling**: Each domain can manage its own product contract

### Anti-Pattern: Implicit Contracts
Avoid: Sharing a table without documentation. Consumers don't know:
- How fresh is the data? (Could be hours old)
- Will this table exist tomorrow? (Is it being retained?)
- Are there PII columns I shouldn't expose to external teams?

---

## 4. Self-Service (Minimal Friction)

### Definition
Teams should be able to discover, request access to, and consume data products with *minimal manual intervention*. Self-service reduces friction and latency.

### In This Implementation

**Discovery Portal** (FastAPI):
```
GET /api/products?query=transaction
├── Search across all domains
├── Filter by SLA, domain, tag
└── Returns: Product name, owner, freshness, availability

GET /api/products/{product_id}
├── Full product spec (schema, quality rules, retention, masking)
├── Owner contact info
└── Current health (freshness lag, quality check pass rate)
```

**Access Requests**:
```
POST /api/access-requests
├── User provides: user_id, role, product_id, justification
├── OPA evaluates: Is auto-approval possible?
│   ├── If yes: Grant immediately, audit log
│   ├── If no: Route to approval workflow (email → owner → approve/deny)
└── Result: User notified via email

Approval workflow SLAs:
├── Standard data: 4-hour approval window
├── Sensitive data (PII): 2-hour approval + security review
```

**Query Execution**:
```sql
-- Analyst runs query (OPA policies silently apply)
SELECT transaction_id, account_holder_name, amount 
FROM transactions.raw_transactions
WHERE booking_timestamp > now() - INTERVAL 7 days;

-- OPA intercepts:
├── Check: Is analyst authorized? → YES
├── Check: Can analyst see account_holder_name? → NO
├── Action: Apply masking (hash value)
├── Audit: Log query, user, rows accessed

-- Result: Returns data with masking applied
transaction_id | account_holder_name       | amount
─────────────────────────────────────────────────
tx_123        | 3f4a9c8b7e2d1f6a5b8c9d0e | 150.00
tx_124        | 9e7d6c5b4a3f2e1d8c9b7a6f | 200.00
```

### Benefits
- **Speed**: Access granted in minutes, not weeks
- **Compliance**: Audit trail automatic; no manual reviews to lose
- **Scalability**: Policy-driven approval, not people-driven
- **User experience**: Portal self-serve, not email chains

### Anti-Pattern: Manual Approval for Everything
Avoid: Every access request → email to compliance team → 2-week wait
This defeats the purpose of decentralized architecture. Use OPA to auto-approve read-only access; only require manual approval for sensitive operations.

---

## Implementation Checklist: Are You Following Data Mesh?

| Principle | Indicator | ✅ This Project |
|-----------|-----------|-----------------|
| **Domain Ownership** | Can a team change their schema without a central approval? | ✅ Yes—each domain manages schema independently |
| | Do teams own their SLAs (not a central platform)? | ✅ Yes—each domain defines freshness, availability |
| **Federated Governance** | Are access rules policy-as-code (not spreadsheets)? | ✅ Yes—OPA Rego policies |
| | Can you add a new data type without modifying policies? | ✅ Yes—policies use attributes, not hard-coded rules |
| **Data Product** | Is the contract explicit (SLAs, masking, retention)? | ✅ Yes—YAML product specs |
| | Do consumers know what they're getting before requesting access? | ✅ Yes—discovery portal shows full spec |
| **Self-Service** | Can a user request access without contacting a person? | ✅ Yes—portal + OPA auto-approval |
| | Can teams query across domains with one SQL engine? | ✅ Yes—unified Spark SQL |

---

## Anti-Patterns to Avoid

### ❌ "We'll centralize governance later"
**Why it fails**: Starting with domain independence, then adding central oversight breaks team autonomy. Policies feel like obstacles.
**Instead**: Encode policies from day 1 (even if simple). OPA policies are cheap to write.

### ❌ "Roles are enough for compliance"
**Why it fails**: New data types (PII, genetic info, financial) don't fit the old role model. You end up with 100+ roles.
**Instead**: Use attribute-based access (data classification + user role + action).

### ❌ "Just give everyone read access, mask in the application"
**Why it fails**: Masking logic spreads across many applications; inconsistent masking; audit trail incomplete.
**Instead**: Enforce masking at the data layer (OPA) so all consumers see consistent masking.

### ❌ "Data mesh means no platform team"
**Why it fails**: Domains still need: catalog, governance engine, metrics infrastructure, discovery. Without platform, you have chaos.
**Instead**: Platform owns *policy enforcement and observability*, not *schema review*. Domains own schema and SLAs.

---

## Next: Dive Deeper

- **[Iceberg Design](iceberg-design.md)** — How to implement domain isolation with schema versioning
- **[Governance & OPA](../platform/governance.md)** — Policy examples and testing
- **[Domain Walkthroughs](../domains/transactions.md)** — See principles in action
- **[Trade-offs](../production/trade-offs.md)** — When data mesh is the right pattern
