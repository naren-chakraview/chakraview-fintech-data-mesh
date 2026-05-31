# Federated Query Guide: Cross-Domain Semantic Analysis

## Overview

This guide explains how to write and execute **federated SPARQL queries** across the fintech semantic mesh domains (Accounts, Transactions, Risk/Compliance). Federated queries enable unified analysis without centralizing data or semantic responsibility.

## What is SPARQL Federation?

SPARQL Federation allows you to query multiple RDF datasets (served by different SPARQL endpoints) as if they were a single dataset. The `SERVICE {}` clause specifies which domain endpoint to query.

**Standard SPARQL:**
```sparql
SELECT ?customer ?name
WHERE {
  ?customer a fintech:Customer ;
            fintech:customerName ?name .
}
```

**Federated SPARQL (across domains):**
```sparql
SELECT ?customer ?name ?riskScore
WHERE {
  SERVICE <http://accounts-domain/sparql> {
    ?customer a fintech:Customer ;
              fintech:customerName ?name .
  }
  SERVICE <http://risk-domain/sparql> {
    ?risk fintech:forCustomer ?customer ;
          fintech:riskScore ?riskScore .
  }
}
```

In the federated version:
- Customer data comes from Accounts domain
- Risk data comes from Risk/Compliance domain
- The SPARQL engine joins results by matching `?customer` across domains

## Query Execution Flow

### 1. Local Binding (Individual Domain Queries)

When SPARQL encounters a `SERVICE` clause, it queries that domain's endpoint independently:

```
Query Plan:
├─ SERVICE <accounts> { Get all customers }
│  └─ Results: [{?customer=<cust_1>, ?name="John"}, ...]
│
├─ SERVICE <risk> { Get risk profiles }
│  └─ Results: [{?risk=<risk_1>, ?customer=<cust_1>, ?riskScore=0.92}, ...]
│
└─ Join on ?customer binding
   └─ Final: [{?customer=<cust_1>, ?name="John", ?riskScore=0.92}, ...]
```

### 2. Variable Binding Across Services

Variables (prefixed with `?`) are the join keys. SPARQL binds variables across SERVICE clauses:

```sparql
WHERE {
  SERVICE <http://accounts-domain/sparql> {
    ?customer a fintech:Customer           # Binds ?customer
  }
  SERVICE <http://transactions-domain/sparql> {
    ?txn fintech:transactionDebtor ?customer  # Uses same ?customer binding
  }
}
```

### 3. Result Aggregation

The SPARQL engine collects results from each service and combines them:

```
Accounts Domain Results        Transactions Domain Results
?customer = <cust_1>    +      ?txn = <txn_001>
?customer = <cust_2>    +      ?txn = <txn_002>
                        +      ?customer = <cust_1>  (from transactionDebtor)
                               ?customer = <cust_1>
                               ?customer = <cust_2>

Join on ?customer:
{?customer=<cust_1>, ?txn=<txn_001>}
{?customer=<cust_1>, ?txn=<txn_002>}
{?customer=<cust_2>, ?txn=<txn_003>}
```

## Writing Cross-Domain Queries: Step-by-Step

### Step 1: Identify Required Data

**Business Question:** "Find customers with failed transactions AND high risk scores"

**Data needed:**
- Customer identity and name → Accounts domain
- Failed transactions → Transactions domain
- Risk score → Risk/Compliance domain

### Step 2: Design the JOIN Strategy

Variables are join keys. Plan which variables link domains:

```
Accounts ←→ Transactions:    via ?customer (transactionDebtor)
Accounts ←→ Risk:            via ?customer (forCustomer)
```

### Step 3: Write Individual SERVICE Blocks

Start simple, add complexity incrementally.

**Service 1: Accounts**
```sparql
SERVICE <http://accounts-domain/sparql> {
  ?customer a fintech:Customer ;
            fintech:customerName ?name .
}
```

**Service 2: Transactions**
```sparql
SERVICE <http://transactions-domain/sparql> {
  ?txn fintech:transactionDebtor ?customer ;
       fintech:transactionStatus "failed" .
}
```

**Service 3: Risk**
```sparql
SERVICE <http://risk-domain/sparql> {
  ?risk fintech:forCustomer ?customer ;
        fintech:riskScore ?riskScore .
  FILTER (?riskScore > 0.8)
}
```

### Step 4: Combine with Shared Variables

Put SERVICE blocks together, using `?customer` to join:

```sparql
SELECT ?customer ?name ?riskScore
WHERE {
  SERVICE <http://accounts-domain/sparql> {
    ?customer a fintech:Customer ;
              fintech:customerName ?name .
  }
  SERVICE <http://transactions-domain/sparql> {
    ?txn fintech:transactionDebtor ?customer ;
         fintech:transactionStatus "failed" .
  }
  SERVICE <http://risk-domain/sparql> {
    ?risk fintech:forCustomer ?customer ;
          fintech:riskScore ?riskScore .
    FILTER (?riskScore > 0.8)
  }
}
```

### Step 5: Add Aggregation and Filtering

```sparql
SELECT ?customer ?name ?riskScore (COUNT(DISTINCT ?txn) AS ?failedCount)
WHERE {
  # ... SERVICE blocks from Step 4 ...
}
GROUP BY ?customer ?name ?riskScore
HAVING (COUNT(DISTINCT ?txn) >= 1)
ORDER BY DESC(?riskScore)
```

## Case Study: Churn Analysis Query

The churn analysis query from `churn-analysis-federated.sparql` is a complete example:

**What it does:**
1. Find customers (Accounts domain)
2. Count their failed payments (Transactions domain)
3. Get their risk score (Risk/Compliance domain)
4. Filter to high-risk customers (riskScore > 0.8)
5. Recommend actions based on risk level

**Key patterns:**
- **Cross-domain linking:** `fintech:transactionDebtor` and `fintech:forCustomer` connect via `?customer`
- **Filtering:** FILTER clause inside SERVICE limits results per domain
- **Aggregation:** GROUP BY and HAVING combine results across domains
- **Binding:** Variables like `?txnDate` are local to SERVICE blocks; `?customer` is shared

## Common Patterns

### Pattern 1: Simple Join

Link data from two domains:

```sparql
SELECT ?customer ?name ?riskScore
WHERE {
  SERVICE <http://accounts-domain/sparql> {
    ?customer fintech:customerName ?name .
  }
  SERVICE <http://risk-domain/sparql> {
    ?risk fintech:forCustomer ?customer ;
          fintech:riskScore ?riskScore .
  }
}
```

### Pattern 2: Multiple Entities in One Domain

Query multiple entity types from one domain:

```sparql
SELECT ?customer ?account ?balance ?txn
WHERE {
  SERVICE <http://accounts-domain/sparql> {
    ?customer a fintech:Customer .
    ?account fintech:accountOwner ?customer ;
             fintech:accountBalance ?balance .
  }
  SERVICE <http://transactions-domain/sparql> {
    ?txn fintech:transactionDebtor ?customer .
  }
}
```

### Pattern 3: Conditional Binding

Use OPTIONAL to include optional data:

```sparql
SELECT ?customer ?riskScore ?complianceStatus
WHERE {
  SERVICE <http://accounts-domain/sparql> {
    ?customer a fintech:Customer .
  }
  SERVICE <http://risk-domain/sparql> {
    ?risk fintech:forCustomer ?customer ;
          fintech:riskScore ?riskScore .
  }
  OPTIONAL {
    SERVICE <http://risk-domain/sparql> {
      ?risk fintech:complianceStatus ?complianceStatus .
    }
  }
}
```

### Pattern 4: Aggregation Across Domains

Count events per entity:

```sparql
SELECT ?customer (COUNT(DISTINCT ?txn) AS ?txnCount)
WHERE {
  SERVICE <http://accounts-domain/sparql> {
    ?customer a fintech:Customer .
  }
  SERVICE <http://transactions-domain/sparql> {
    ?txn fintech:transactionDebtor ?customer .
  }
}
GROUP BY ?customer
```

## Performance Considerations

### Query Optimization

1. **Filter Early:** Push FILTER clauses inside SERVICE blocks to reduce transferred data
   ```sparql
   # Good: Filter in service
   SERVICE <http://risk-domain/sparql> {
     ?risk fintech:forCustomer ?customer ;
           fintech:riskScore ?riskScore .
     FILTER (?riskScore > 0.8)   # ← Filter at source
   }

   # Expensive: Filter after transfer
   SERVICE <http://risk-domain/sparql> {
     ?risk fintech:forCustomer ?customer ;
           fintech:riskScore ?riskScore .
   }
   FILTER (?riskScore > 0.8)   # ← Filters after all data returned
   ```

2. **Limit Results:** Use LIMIT to cap transferred data
   ```sparql
   SERVICE <http://accounts-domain/sparql> {
     ?customer a fintech:Customer .
   }
   LIMIT 1000
   ```

3. **Select Specific Properties:** Only retrieve needed properties
   ```sparql
   # Good: Select specific properties
   SERVICE <http://accounts-domain/sparql> {
     ?customer fintech:customerName ?name ;
               fintech:customerEmail ?email .
   }

   # Expensive: Wildcard returns all properties
   SERVICE <http://accounts-domain/sparql> {
     ?customer ?p ?v .
   }
   ```

### Network Latency

Each SERVICE block makes a network request. Minimize round-trips:

- Combine related filters into one SERVICE block (not multiple)
- Avoid querying the same service multiple times for similar data

### Result Set Size

Large result sets from individual domains multiply when joined:

```
Service A: 1,000 customers
Service B: 10,000 transactions
Service C: 500 risk profiles

Worst case join: 1,000 × 10,000 × 500 = 5 billion rows
(In practice, WHERE clause filters this dramatically)
```

Use GROUP BY and HAVING to aggregate early.

## Troubleshooting

### Issue: Query Returns No Results

**Possible causes:**
1. Variable names don't match across SERVICE blocks
2. IRIs don't match (case-sensitive)
3. Data doesn't exist in one or more domains
4. FILTER is too restrictive

**Solution:**
- Run each SERVICE block independently to verify data exists
- Check IRI formats (e.g., `<https://...>` vs `https://...`)
- Loosen FILTER conditions temporarily to verify joins work

### Issue: Query Times Out

**Possible causes:**
1. One domain endpoint is slow
2. Query transfers too much data
3. Federation engine can't optimize the query

**Solution:**
- Check endpoint response time: `curl http://endpoint/sparql?query=SELECT%201`
- Add LIMIT to reduce transferred data
- Move FILTER clauses inside SERVICE blocks
- Run individual SERVICE queries to identify bottleneck

### Issue: Variable Binding Fails

**Symptom:** Variables have no values in results

**Cause:** Variable binding paths don't exist

```sparql
# ✗ This binds ?customer from Service 1, but Service 2 uses different binding
SERVICE <http://accounts-domain/sparql> {
  ?customer a fintech:Customer .
}
SERVICE <http://transactions-domain/sparql> {
  ?txn fintech:transactionDebtor ?payer .   # ← Wrong variable, won't join
}

# ✓ Correct: Use same variable name
SERVICE <http://accounts-domain/sparql> {
  ?customer a fintech:Customer .
}
SERVICE <http://transactions-domain/sparql> {
  ?txn fintech:transactionDebtor ?customer .   # ← Joins via ?customer
}
```

## Running Queries

### Via Command Line

```bash
python run-churn-analysis.py --format table
```

### Via Python API

```python
from federated_query_client import FederatedQueryClient

endpoints = {
    "accounts": "http://localhost:3030/accounts/sparql",
    "transactions": "http://localhost:3031/transactions/sparql",
    "risk": "http://localhost:3032/risk_compliance/sparql"
}

client = FederatedQueryClient(endpoints)

# Load and execute query
with open("churn-analysis-federated.sparql") as f:
    query = f.read()

results = client.execute_query(query)
print(client.format_results(results))
```

### Via curl

```bash
curl -X GET \
  --data-urlencode "query@churn-analysis-federated.sparql" \
  http://localhost:3030/accounts/sparql \
  -H "Accept: application/sparql-results+json"
```

## References

- [SPARQL 1.1 Federated Query](https://www.w3.org/TR/sparql11-federated-query/)
- [RDF Concepts](https://www.w3.org/TR/rdf-concepts/)
- [Fintech Semantic Integration Case Study](./case-study-guide.md)
