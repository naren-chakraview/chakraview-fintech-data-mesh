# Discovery Portal & Self-Service

Self-service data product discovery and access request management.

---

## Overview

The Discovery Portal is a FastAPI service enabling data consumers to:
1. **Find** data products (search, filter by domain/tag/SLA)
2. **Understand** contracts (SLAs, quality rules, retention, masking)
3. **Request access** (with approval workflows)
4. **Track status** (access request lifecycle)

**Architecture**:
```
┌─────────────────────────────────────────────┐
│   Discovery Portal (FastAPI)                │
│   ├── /api/products (search, list)         │
│   ├── /api/products/{id} (details)         │
│   ├── /api/access-requests (submit, track) │
│   └── /api/health (liveness)               │
└─────────────────────────────────────────────┘
         ↓                    ↓
[Elasticsearch]         [OPA Policies]
(product catalog)       (auto-approval logic)
```

---

## Product Search

### Endpoint: GET /api/products

**Query Parameters**:
- `query` (optional): Free-text search (name, description, tags)
- `domain` (optional): Filter by domain (transactions, accounts, etc.)
- `tag` (optional): Filter by tag (external-feed, pii, high-frequency)
- `min_freshness_minutes` (optional): Minimum freshness SLA
- `include_restricted` (optional): Include restricted data (requires approval)

**Response**:
```json
{
  "total": 5,
  "results": [
    {
      "id": "transaction-feed",
      "name": "Transaction Feed",
      "domain": "transactions",
      "owner": "transactions@chakra.fintech",
      "freshness_sla_minutes": 5,
      "availability_sla_percent": 99.9,
      "retention_years": 7,
      "has_pii": true,
      "has_restricted_data": false,
      "tags": ["payments", "real-time", "high-volume"],
      "description": "Real-time transaction events with settlement status...",
      "access_required": false,
      "approval_sla_hours": null
    },
    {
      "id": "fraud-scores",
      "name": "Fraud Scoring",
      "domain": "risk_compliance",
      "owner": "risk-compliance@chakra.fintech",
      "freshness_sla_minutes": 10,
      "availability_sla_percent": 99.99,
      "retention_years": 10,
      "has_pii": true,
      "has_restricted_data": true,
      "tags": ["fraud-detection", "restricted"],
      "description": "ML-based fraud risk scores...",
      "access_required": true,
      "approval_sla_hours": 2
    }
  ]
}
```

### Example Queries

```bash
# Find all transaction-related products
curl 'http://localhost:8000/api/products?query=transaction'

# Find products in risk/compliance domain
curl 'http://localhost:8000/api/products?domain=risk_compliance'

# Find high-frequency data products
curl 'http://localhost:8000/api/products?tag=high-frequency&min_freshness_minutes=5'

# Find products I can access without approval
curl 'http://localhost:8000/api/products?access_required=false'
```

---

## Product Details

### Endpoint: GET /api/products/{product_id}

**Response**:
```json
{
  "id": "transaction-feed",
  "name": "Transaction Feed",
  "version": "1.0",
  "domain": "transactions",
  "owner_email": "transactions@chakra.fintech",
  "owner_contact": {
    "name": "Transactions Domain Team",
    "slack": "#transactions-data",
    "email": "transactions@chakra.fintech"
  },
  
  "description": "Real-time transaction events for fraud detection, settlement, and analytics.",
  
  "tables": [
    {
      "name": "raw_transactions",
      "iceberg_table": "transactions.raw_transactions",
      "schema_version": "2.1",
      "doc": "Raw transaction events with all fields",
      "partitions": ["year", "month", "day", "account_id"],
      "record_count": 5000000000,
      "size_gb": 150
    }
  ],
  
  "schema": {
    "transaction_id": {"type": "string", "classification": "public"},
    "account_id": {"type": "string", "classification": "pii"},
    "amount": {"type": "double", "classification": "public"},
    "merchant_id": {"type": "string", "classification": "confidential"},
    "booking_timestamp": {"type": "long", "classification": "public"},
    "status": {"type": "string", "classification": "public"}
  },
  
  "sla": {
    "freshness": {"value": 5, "unit": "minutes"},
    "availability": {"value": 99.9, "unit": "percent"},
    "completeness": {"value": 99, "unit": "percent"}
  },
  
  "quality_rules": [
    {
      "name": "positive_amount",
      "rule": "amount > 0",
      "impact": "critical",
      "description": "Transactions must have positive amount"
    },
    {
      "name": "valid_settlement_date",
      "rule": "booking_date <= settlement_date",
      "impact": "high"
    }
  ],
  
  "access_policy": {
    "default": "deny",
    "approval_required": false,
    "approval_sla_hours": null,
    "masked_columns": [
      {
        "name": "account_id",
        "classification": "pii",
        "masked_for_roles": ["external_analyst", "contractor"],
        "masking_strategy": "full_hash"
      },
      {
        "name": "merchant_id",
        "classification": "confidential",
        "masked_for_roles": ["external_analyst"],
        "masking_strategy": "partial_hash"
      }
    ]
  },
  
  "retention": {
    "value": 7,
    "unit": "years",
    "reason": "SOX compliance requirement"
  },
  
  "downstream_consumers": [
    {
      "name": "fraud-detection-service",
      "type": "real-time",
      "sla": "< 1 second"
    },
    {
      "name": "compliance-reporting",
      "type": "batch",
      "frequency": "quarterly"
    }
  ],
  
  "current_health": {
    "freshness_lag_minutes": 2.3,
    "availability_percent": 99.95,
    "last_snapshot": "2026-04-30T11:40:00Z",
    "quality_check_pass_rate": 99.8,
    "rows_last_24h": 432000000
  },
  
  "query_examples": [
    "SELECT transaction_id, amount FROM transactions.raw_transactions WHERE booking_timestamp > now() - INTERVAL 7 days",
    "SELECT COUNT(*) FROM transactions.raw_transactions WHERE status = 'FAILED'"
  ],
  
  "tags": ["payments", "real-time", "high-volume", "pci-compliant"],
  "last_updated": "2026-04-30T09:00:00Z"
}
```

---

## Access Requests

### Endpoint: POST /api/access-requests

**Request Body**:
```json
{
  "user_id": "analyst_42",
  "user_email": "analyst.42@company.com",
  "user_role": "external_analyst",
  "data_product_id": "transaction-feed",
  "action": "read",
  "justification": "Weekly fraud pattern analysis for risk committee",
  "requested_columns": ["transaction_id", "amount", "status"],
  "start_date": "2026-05-01",
  "end_date": "2026-06-30"
}
```

**Response** (Immediate):
```json
{
  "request_id": "req_abc123def456",
  "status": "pending_evaluation",
  "evaluation_status": "auto-approval_check",
  "created_at": "2026-04-30T11:45:00Z",
  "estimated_decision_time": "2026-04-30T15:45:00Z",
  "message": "Your request is being evaluated against access policies..."
}
```

### OPA Evaluation (Automatic)

```
Policy Evaluation Flow:

1. Check: Is user authorized?
   ├── Role: external_analyst
   ├── Action: read
   ├── Data classification: public (transaction_id, amount, status)
   ├── Result: YES, authorized

2. Check: Is approval needed?
   ├── Data classification: public (no sensitive columns)
   ├── Result: NO, auto-approve

3. Decision: AUTO_APPROVED
   ├── Access granted immediately
   ├── User notified: "Access granted"
   ├── Audit logged
   └── SLA compliance: Approved at T+0 (target: < 4 hours)
```

### Response (After OPA Decision)

**Auto-Approved**:
```json
{
  "request_id": "req_abc123def456",
  "status": "approved",
  "approval_type": "auto",
  "approved_at": "2026-04-30T11:45:15Z",
  "approved_by": "system",
  "message": "Access approved automatically",
  "access_details": {
    "data_product": "transaction-feed",
    "columns_granted": ["transaction_id", "amount", "status"],
    "columns_masked": [],
    "masking_applied": false,
    "valid_from": "2026-04-30T11:45:15Z",
    "valid_until": "2026-06-30T23:59:59Z",
    "connection_string": "jdbc:iceberg://catalog/transactions.raw_transactions"
  },
  "next_steps": [
    "You can now query the data",
    "Use Spark SQL: SELECT * FROM transactions.raw_transactions",
    "Queries will be logged to Elasticsearch for audit"
  ]
}
```

**Requires Approval**:
```json
{
  "request_id": "req_xyz789abc123",
  "status": "pending_approval",
  "approval_type": "manager",
  "created_at": "2026-04-30T11:45:00Z",
  "estimated_decision_time": "2026-04-30T13:45:00Z",
  "approval_sla_hours": 2,
  "assigned_to": "risk-compliance@chakra.fintech",
  "message": "Your request requires approval from the data owner",
  "justification_visible_to_approver": "Weekly fraud pattern analysis for risk committee",
  "next_steps": [
    "The data owner (risk-compliance@chakra.fintech) will review your request",
    "Check your email for updates",
    "You will be notified once approved or denied"
  ]
}
```

### Endpoint: GET /api/access-requests/{request_id}

Track approval status:
```json
{
  "request_id": "req_xyz789abc123",
  "status": "pending_approval",
  "created_at": "2026-04-30T11:45:00Z",
  "approval_sla": {
    "target_time": "2026-04-30T13:45:00Z",
    "time_remaining_minutes": 45,
    "status": "on_track"
  },
  "timeline": [
    {
      "event": "requested",
      "timestamp": "2026-04-30T11:45:00Z",
      "actor": "analyst_42"
    },
    {
      "event": "evaluation_started",
      "timestamp": "2026-04-30T11:45:15Z",
      "actor": "system"
    },
    {
      "event": "requires_approval",
      "timestamp": "2026-04-30T11:45:30Z",
      "actor": "system",
      "reason": "Restricted data requires manager approval"
    },
    {
      "event": "routed_to_approver",
      "timestamp": "2026-04-30T11:45:45Z",
      "actor": "system",
      "routed_to": "risk-compliance@chakra.fintech"
    }
  ]
}
```

---

## Query Examples from Portal

### Example 1: Risk Analyst Workflow

```bash
# Step 1: Find fraud scoring products
curl 'http://localhost:8000/api/products?query=fraud'

# Step 2: Get details
curl 'http://localhost:8000/api/products/fraud-scores'

# Step 3: Request access (auto-approved for risk analysts)
curl -X POST 'http://localhost:8000/api/access-requests' \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "risk_analyst_5",
    "user_role": "risk_analyst",
    "data_product_id": "fraud-scores",
    "action": "read",
    "justification": "Daily fraud monitoring"
  }'

# Step 4: Check status (immediately approved)
curl 'http://localhost:8000/api/access-requests/req_12345'

# Step 5: Query (in Spark SQL)
spark.sql("""
  SELECT fraud_score, risk_level, COUNT(*) as count
  FROM risk_compliance.fraud_scores
  WHERE evaluated_at > now() - INTERVAL 1 day
  GROUP BY fraud_score, risk_level
  ORDER BY fraud_score DESC
""")
```

### Example 2: External Analyst Workflow

```bash
# Step 1: Search products
curl 'http://localhost:8000/api/products?query=transaction&access_required=false'

# Step 2: Get details (note: masking_required = true for account_id)
curl 'http://localhost:8000/api/products/transaction-feed'

# Step 3: Request access
curl -X POST 'http://localhost:8000/api/access-requests' \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "external_analyst_8",
    "user_role": "external_analyst",
    "data_product_id": "transaction-feed",
    "action": "read",
    "justification": "Custom analytics report for management"
  }'

# Step 4: Check status (auto-approved)
curl 'http://localhost:8000/api/access-requests/req_67890'

# Step 5: Query (masking applied automatically by OPA)
spark.sql("""
  SELECT transaction_id, amount, status
  FROM transactions.raw_transactions
  WHERE booking_timestamp > now() - INTERVAL 7 days
  LIMIT 1000
""")

# Result: account_id column omitted (masked)
transaction_id        | amount  | status
──────────────────────────────────────────
tx_abc123def456...    | 150.00  | CLEARED
tx_xyz789abc123...    | 200.00  | PENDING
```

---

## Portal API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/products` | GET | List/search products |
| `/api/products/{id}` | GET | Product details + schema + SLAs |
| `/api/products/{id}/health` | GET | Current product health (lag, quality) |
| `/api/access-requests` | POST | Submit access request |
| `/api/access-requests/{id}` | GET | Track request status |
| `/api/access-requests/{id}/approve` | POST | Approve (admin only) |
| `/api/access-requests/{id}/deny` | POST | Deny (admin only) |
| `/api/my-access` | GET | List my current access |
| `/api/my-requests` | GET | List my pending/historical requests |
| `/api/health` | GET | Portal health check |

---

## Implementation

```python
# From platform/discovery/backend/main.py

from fastapi import FastAPI, Query, HTTPException
from typing import Optional, List
import requests
import json

app = FastAPI(title="Data Product Discovery Portal")

@app.get("/api/products")
async def list_products(
    query: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    tag: Optional[str] = Query(None)
):
    """Search products by name, domain, or tag"""
    # Query Elasticsearch for products matching criteria
    filters = {}
    if domain:
        filters["domain"] = domain
    if tag:
        filters["tags"] = tag
    
    results = elasticsearch.search(
        index="data_products",
        q=query if query else "*",
        filters=filters
    )
    
    return {
        "total": len(results),
        "results": results
    }

@app.post("/api/access-requests")
async def submit_access_request(request: AccessRequest):
    """Submit an access request"""
    
    # Evaluate OPA policy
    opa_decision = requests.post(
        f"{OPA_URL}/v1/data/authz/evaluate",
        json={
            "input": {
                "user_id": request.user_id,
                "user_role": request.user_role,
                "action": request.action,
                "domain": request.domain,
                "table": request.table,
                "data_classification": request.data_classification
            }
        }
    ).json()
    
    if opa_decision["result"]["allow"]:
        if not opa_decision["result"].get("requires_approval"):
            # Auto-approve
            return {
                "request_id": generate_id(),
                "status": "approved",
                "approval_type": "auto",
                "approved_at": now()
            }
        else:
            # Route to approval workflow
            return {
                "request_id": generate_id(),
                "status": "pending_approval",
                "approval_type": "manager",
                "assigned_to": request.domain_owner_email,
                "estimated_decision_time": now() + timedelta(hours=4)
            }
    else:
        return {
            "request_id": generate_id(),
            "status": "denied",
            "reason": opa_decision["result"].get("reason", "Access denied")
        }
```

---

## Next

- **[Governance](governance.md)** — How OPA makes approval decisions
- **[Observability](observability.md)** — Monitor access request SLAs
