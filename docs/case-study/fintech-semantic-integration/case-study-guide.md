# Fintech Semantic Integration: Case Study Execution Guide

## Overview

This case study demonstrates how to solve a critical business problem in fintech: **identifying high-value customers with churn risk signals across three autonomous domains without centralizing data ownership or transformation logic.**

### The Business Problem

A fintech platform operates with three independent business domains:
- **Accounts Domain**: Owns customer account information and identity
- **Transactions Domain**: Owns payment and transaction history
- **Risk/Compliance Domain**: Owns regulatory risk profiles and support escalations

Each domain manages its own data, systems, and SPARQL endpoint. To identify customers at risk of churn, the business needs to correlate signals across all three domains:
- Support escalation frequency (from Risk/Compliance)
- Recent transaction failures (from Transactions)
- Risk assessment scores (from Risk/Compliance)

**Traditional Approach (Problematic)**:
- Copy data from each domain to a central data warehouse
- Run transformation logic in the warehouse
- Lose domain autonomy, increase coupling, create governance bottlenecks

**Semantic Integration Approach**:
- Each domain maintains its own SPARQL endpoint and RDF data
- Domains link entities via shared URIs (customer identifiers)
- Execute federated SPARQL queries that join across endpoints
- Zero central transformation, full domain autonomy

## Architecture & Domain Collaboration

### Three-Domain Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SPARQL Federation                             │
│  Federated Query Engine (e.g., Fuseki, GraphDB Service Endpoint)     │
└─────────────────────────────────────────────────────────────────────┘
                    ↓ SERVICE clauses ↓
        ┌───────────────┬───────────────┬───────────────┐
        │               │               │               │
  ┌─────────────┐ ┌──────────────┐ ┌─────────────────┐
  │  Accounts   │ │ Transactions │ │ Risk/Compliance │
  │   Domain    │ │    Domain    │ │     Domain      │
  │             │ │              │ │                 │
  │ SPARQL:3030 │ │ SPARQL:3030  │ │ SPARQL:3030     │
  │ /accounts   │ │ /transactions│ │ /risk           │
  └─────────────┘ └──────────────┘ └─────────────────┘
        ↓               ↓                    ↓
    [RDF Store]    [RDF Store]          [RDF Store]
        ↓               ↓                    ↓
    Customer:      Transaction:        RiskProfile:
    - Customers    - Payments          - Risk Scores
    - Accounts     - Counterparties    - Support Tickets
```

### How Domains Collaborate

#### 1. Accounts Domain (Customer Identity & Ownership)

**Responsibility**: Owns customer master data and mints customer IRIs
- Maintains `fintech:Customer` entities with unique IRIs
- Example IRI: `<https://accounts.fintech.local/customer/cust_12345>`
- Publishes customer attributes: name, email, account status, registration date
- Serves SPARQL endpoint at `http://localhost:3030/accounts/sparql`

**RDF Pattern**:
```turtle
@prefix fintech: <https://chakracommerce.com/ontology/fintech/> .

<https://accounts.fintech.local/customer/cust_12345> a fintech:Customer ;
    fintech:customerName "John Doe" ;
    fintech:customerEmail "john@acme.com" ;
    fintech:accountStatus "active" ;
    fintech:registrationDate "2020-01-15"^^xsd:date .
```

#### 2. Transactions Domain (Payment History)

**Responsibility**: Owns transaction data and links to customers via Accounts IRIs
- Maintains `fintech:Transaction` entities
- Each transaction links to customer via `fintech:transactionDebtor` property
- Uses **same customer IRI** as Accounts domain for linking
- Example: `?transaction fintech:transactionDebtor <https://accounts.fintech.local/customer/cust_12345>`
- Serves SPARQL endpoint at `http://localhost:3030/transactions/sparql`

**RDF Pattern**:
```turtle
<https://transactions.fintech.local/txn/txn_98765> a fintech:Transaction ;
    fintech:transactionDebtor <https://accounts.fintech.local/customer/cust_12345> ;
    fintech:transactionAmount 1500.00 ;
    fintech:transactionStatus "failed" ;
    fintech:transactionDate "2026-05-28"^^xsd:dateTime ;
    fintech:failureReason "Insufficient Funds" .
```

**Critical**: The `?transactionDebtor` links to the **exact same IRI** that Accounts domain publishes. This shared URI enables joining across domains.

#### 3. Risk/Compliance Domain (Regulatory & Support)

**Responsibility**: Owns risk profiles and support escalation data, links to customers
- Maintains `fintech:RiskProfile` entities
- Links to customers via `fintech:forCustomer` property
- Maintains `fintech:SupportTicket` entities for escalations
- Computes `fintech:riskScore` based on regulatory signals
- Serves SPARQL endpoint at `http://localhost:3030/risk/sparql`

**RDF Pattern**:
```turtle
<https://risk.fintech.local/profile/risk_54321> a fintech:RiskProfile ;
    fintech:forCustomer <https://accounts.fintech.local/customer/cust_12345> ;
    fintech:riskScore 0.85 ;
    fintech:riskCategory "CUSTOMER_DISSATISFACTION" ;
    fintech:lastUpdated "2026-05-30"^^xsd:dateTime .

<https://risk.fintech.local/ticket/ticket_111> a fintech:SupportTicket ;
    fintech:forCustomer <https://accounts.fintech.local/customer/cust_12345> ;
    fintech:ticketReason "Billing Dispute" ;
    fintech:createdDate "2026-05-25"^^xsd:dateTime ;
    fintech:escalationFlag true .
```

### Key Architectural Principles

1. **Single Source of Truth for Customer Identity**: Only Accounts domain mints customer IRIs
2. **Shared Ontology**: All domains use the same namespace (`https://chakracommerce.com/ontology/fintech/`)
3. **URI-Based Linking**: Cross-domain references use full, resolvable URIs (not IDs)
4. **Domain Autonomy**: No shared database, no replication, no ETL dependencies
5. **Loose Coupling**: Domains only need to know about shared entity types, not each other's implementations
6. **No Central Transformation**: SPARQL Federation queries handle all joining and aggregation

## Churn Signals: Definition & Thresholds

A customer is identified as a **churn risk** when they exhibit ALL of the following signals:

| Signal | Source Domain | Threshold | Rationale |
|--------|---------------|-----------|-----------|
| Support Escalations | Risk/Compliance | 3+ in last 30 days | Frequent escalations indicate dissatisfaction |
| Failed Transactions | Transactions | 1+ in last 30 days | Payment failures frustrate customers |
| Risk Score | Risk/Compliance | > 0.8 (high risk) | Compliance system identifies unstable accounts |

**Combined Signal**: A customer qualifies for retention outreach if they have:
- **AND**: 3+ support escalations in the last 30 days
- **AND**: 1+ failed transactions in the last 30 days
- **AND**: Risk score exceeding 0.8

This multi-signal approach reduces false positives and focuses on genuinely at-risk customers.

## Step-by-Step Execution

This section walks through the complete process of standing up the three domains, loading data, and executing the federated query.

### Step 1: Start Accounts Domain

Start the Accounts domain SPARQL endpoint and database.

**Prerequisites**: Docker and Docker Compose installed

**Command**:
```bash
cd /home/gundu/portfolio/chakraview-fintech-data-mesh/domains/accounts
docker-compose up -d
```

**Expected Output**:
```
Creating accounts-postgres ... done
Creating accounts-fuseki ... done
```

**Verify Health**:
```bash
# Check Postgres readiness
docker exec accounts-postgres pg_isready

# Wait for Fuseki to be ready (should return 200)
curl -s http://localhost:3030/
```

**Success Criteria**: Both containers running, Fuseki responds to HTTP requests

### Step 2: Load Accounts Sample Data

Load customer and account master data into the Accounts domain.

**Command**:
```bash
cd /home/gundu/portfolio/chakraview-fintech-data-mesh/domains/accounts

# Load CSV data into Postgres
docker exec accounts-postgres psql -U postgres -d accounts_db -c \
  "\COPY customers (customer_id, name, email, status, registration_date) \
   FROM STDIN WITH (FORMAT csv, HEADER true)" < data/accounts-customers.csv

docker exec accounts-postgres psql -U postgres -d accounts_db -c \
  "\COPY accounts (account_id, customer_id, account_type, balance) \
   FROM STDIN WITH (FORMAT csv, HEADER true)" < data/accounts-accounts.csv
```

**Data Loaded**:
- `accounts-customers.csv`: Contains 5 sample customers (john@acme.com, alice@tech.com, etc.)
- `accounts-accounts.csv`: Contains 5 account records linked to customers

**Trigger RDF Transformation**:
```bash
# Invoke transformation job (via API or message queue)
# This converts Postgres rows to RDF and loads into Fuseki
curl -X POST http://localhost:8080/transform/accounts

# Or trigger via Kafka message
echo '{"type":"transformation_request","domain":"accounts"}' | \
  docker exec -i accounts-kafka kafka-console-producer --broker-list localhost:9092 --topic transformations
```

**Verify Data in SPARQL**:
```bash
# Query the Accounts SPARQL endpoint
curl -X GET "http://localhost:3030/accounts/sparql?query=\
SELECT%20%3Fcustomer%20%3Fname%20WHERE%20%7B%0A%20%20%3Fcustomer%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FCustomer%3E%20%3B%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FcustomerName%3E%20%3Fname%20.%0A%7D"

# Expected: 5 results with customer URIs and names
```

**Success Criteria**: SPARQL endpoint responds with 5 customer records

### Step 3: Start Transactions Domain

Start the Transactions domain SPARQL endpoint and database.

**Command**:
```bash
cd /home/gundu/portfolio/chakraview-fintech-data-mesh/domains/transactions
docker-compose up -d
```

**Expected Output**:
```
Creating transactions-postgres ... done
Creating transactions-fuseki ... done
```

**Verify Health**:
```bash
curl -s http://localhost:3031/
```

**Load Transactions Sample Data**:
```bash
# Load transaction and counterparty data
docker exec transactions-postgres psql -U postgres -d transactions_db -c \
  "\COPY payments (txn_id, customer_id, amount, status, date) \
   FROM STDIN WITH (FORMAT csv, HEADER true)" < data/transactions-payments.csv

docker exec transactions-postgres psql -U postgres -d transactions_db -c \
  "\COPY counterparties (cp_id, customer_id, name) \
   FROM STDIN WITH (FORMAT csv, HEADER true)" < data/transactions-counterparties.csv

# Trigger RDF transformation with customer IRI linking
curl -X POST http://localhost:8081/transform/transactions
```

**Critical**: During transformation, the Transactions domain must resolve `customer_id` to the customer IRIs minted by the Accounts domain.
- Transformation queries Accounts SPARQL endpoint for each customer_id
- Retrieves the corresponding customer IRI
- Links all transactions to that IRI via `fintech:transactionDebtor`

**Verify Data in SPARQL**:
```bash
curl -X GET "http://localhost:3031/transactions/sparql?query=\
SELECT%20%3Ftxn%20%3Fcustomer%20%3Famount%20WHERE%20%7B%0A%20%20%3Ftxn%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FTransaction%3E%20%3B%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FtransactionDebtor%3E%20%3Fcustomer%20%3B%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FtransactionAmount%3E%20%3Famount%20.%0A%7D"

# Expected: Transactions with customer IRIs that match Accounts domain IRIs
```

**Success Criteria**: SPARQL endpoint responds with transactions linked to correct customer IRIs

### Step 4: Start Risk/Compliance Domain

Start the Risk/Compliance domain SPARQL endpoint and database.

**Command**:
```bash
cd /home/gundu/portfolio/chakraview-fintech-data-mesh/domains/risk-compliance
docker-compose up -d
```

**Expected Output**:
```
Creating risk-postgres ... done
Creating risk-fuseki ... done
```

**Verify Health**:
```bash
curl -s http://localhost:3032/
```

**Load Risk Sample Data**:
```bash
# Load risk profiles and support tickets
docker exec risk-postgres psql -U postgres -d risk_db -c \
  "\COPY risk_profiles (profile_id, customer_id, risk_score, category) \
   FROM STDIN WITH (FORMAT csv, HEADER true)" < data/risk-profiles.csv

docker exec risk-postgres psql -U postgres -d risk_db -c \
  "\COPY support_tickets (ticket_id, customer_id, reason, created_date, escalation_flag) \
   FROM STDIN WITH (FORMAT csv, HEADER true)" < data/support-tickets.csv

# Trigger RDF transformation with customer IRI linking
curl -X POST http://localhost:8082/transform/risk
```

**Critical**: Like the Transactions domain, Risk/Compliance must resolve customer_id to Accounts domain IRIs:
- During RDF transformation, query Accounts SPARQL endpoint for each customer_id
- Retrieve the corresponding customer IRI
- Link all risk profiles and tickets via `fintech:forCustomer`

**Verify Data in SPARQL**:
```bash
curl -X GET "http://localhost:3032/risk/sparql?query=\
SELECT%20%3Fprofile%20%3Fcustomer%20%3FriskScore%20WHERE%20%7B%0A%20%20%3Fprofile%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FRiskProfile%3E%20%3B%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FforCustomer%3E%20%3Fcustomer%20%3B%0A%20%20%20%20%20%20%20%20%20%20%20%20%20%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FriskScore%3E%20%3FriskScore%20.%0A%7D"

# Expected: Risk profiles with customer IRIs matching Accounts domain
```

**Success Criteria**: SPARQL endpoint responds with risk profiles linked to correct customer IRIs

### Step 5: Execute Federated Query

Execute the churn analysis query against all three endpoints simultaneously using SPARQL Federation.

**Command**:
```bash
# Option A: Via curl (recommended for debugging)
curl -X GET "http://localhost:3030/accounts/sparql?query=$(cat domains/federation/queries/churn-analysis-federated.sparql | jq -sRr @uri)"

# Option B: Using a SPARQL client library (Python, Node.js, etc.)
# See domains/federation/queries/run-federated-query.py for example

# Option C: Via Apache Jena command-line tools
arq --query domains/federation/queries/churn-analysis-federated.sparql \
    --results csv
```

**Query File**: `domains/federation/queries/churn-analysis-federated.sparql`

**Query Logic**:
```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?customer ?customerName ?failedTxnCount ?escalationCount ?riskScore
WHERE {
  # SERVICE 1: Get customer information from Accounts domain
  SERVICE <http://localhost:3030/accounts/sparql> {
    ?customer a fintech:Customer ;
              fintech:customerName ?customerName ;
              fintech:customerEmail ?email .
  }
  
  # SERVICE 2: Count recent failed transactions from Transactions domain
  SERVICE <http://localhost:3030/transactions/sparql> {
    ?txn fintech:transactionDebtor ?customer ;
         fintech:transactionStatus "failed" ;
         fintech:transactionDate ?txnDate .
    FILTER (?txnDate >= "2026-04-30"^^xsd:dateTime)
  }
  
  # SERVICE 3: Get risk information from Risk/Compliance domain
  SERVICE <http://localhost:3030/risk/sparql> {
    ?riskProfile fintech:forCustomer ?customer ;
                 fintech:riskScore ?riskScore .
    FILTER (?riskScore > 0.8)
    
    # Count support escalations
    ?ticket fintech:forCustomer ?customer ;
            fintech:escalationFlag true ;
            fintech:createdDate ?ticketDate .
    FILTER (?ticketDate >= "2026-04-30"^^xsd:dateTime)
  }
}
GROUP BY ?customer ?customerName ?riskScore
HAVING (COUNT(DISTINCT ?txn) >= 1 && COUNT(DISTINCT ?ticket) >= 3)
ORDER BY DESC(?riskScore)
```

**Expected Execution Flow**:
1. Query engine parses the SPARQL and identifies three SERVICE clauses
2. Each SERVICE clause is sent to its respective endpoint in parallel (or sequentially)
3. Accounts domain returns: customer URIs and names
4. Transactions domain returns: failed transactions for each customer, filtered by date
5. Risk domain returns: risk profiles and support tickets, filtered by thresholds
6. Results are joined on `?customer` variable
7. GROUP BY aggregates counts per customer
8. HAVING filters for customers with 1+ failed txns AND 3+ escalations
9. Final results sorted by risk score

**Success Criteria**: Query executes without timeout, returns churn candidates

## Expected Results

The federated query should return customers matching the churn signal criteria.

### Sample Output Table

| Customer IRI | Customer Name | Failed Txns (30d) | Escalations (30d) | Risk Score | Action |
|---|---|---|---|---|---|
| `https://accounts.fintech.local/customer/cust_12345` | john@acme.com | 1 | 3 | 0.85 | Retention Outreach |
| `https://accounts.fintech.local/customer/cust_67890` | alice@tech.com | 2 | 4 | 0.92 | Immediate Escalation |
| `https://accounts.fintech.local/customer/cust_24680` | bob@startup.io | 1 | 3 | 0.81 | Retention Outreach |

### Understanding the Output

- **Customer IRI**: The unique identifier minted by Accounts domain (resolvable to customer details)
- **Customer Name**: Retrieved from Accounts domain (used for outreach teams)
- **Failed Txns (30d)**: Count of failed transactions in last 30 days from Transactions domain
- **Escalations (30d)**: Count of escalated support tickets in last 30 days from Risk domain
- **Risk Score**: Compliance risk score from Risk domain (0-1 scale, >0.8 = high risk)
- **Action**: Recommended next step based on severity of signals

### Why These Results?

**john@acme.com** (Risk Score: 0.85):
- Recent payment failure (may indicate account issues)
- Multiple recent support escalations (customer dissatisfaction)
- High compliance risk score (flagged by risk model)
- **Conclusion**: Customer is genuinely at risk; recommend proactive outreach

**alice@tech.com** (Risk Score: 0.92):
- Multiple payment failures (transaction instability)
- Most escalations of the cohort (high frustration)
- Highest risk score (severe compliance concerns)
- **Conclusion**: Most urgent case; escalate to customer success team immediately

## Interpreting Results

### What the Churn Signals Tell Us

Each signal contributes different information about customer health:

#### Failed Transactions (from Transactions domain)
- **Indicates**: Customer is experiencing friction with the payment system
- **Suggests**: System issues, account restrictions, or insufficient funds
- **Action**: Troubleshoot technical issues, verify account status

#### Support Escalations (from Risk/Compliance domain)
- **Indicates**: Customer frustration has escalated beyond first-line support
- **Suggests**: Unresolved issues, dissatisfaction with service
- **Action**: Investigate root cause, consider service recovery

#### High Risk Score (from Risk/Compliance domain)
- **Indicates**: Regulatory, compliance, or behavioral risk detected
- **Suggests**: Account instability, policy violations, or fraud signals
- **Action**: Compliance review, account audit, or monitoring escalation

### Combined Signal Interpretation

When all three signals are present, it indicates a **systemic problem**, not a transient issue:

```
Failed Txns + Escalations + High Risk Score = Churn Risk
```

This customer is likely to either:
1. **Close their account** (churn)
2. **Reduce usage** (negative revenue impact)
3. **Leave negative reviews** (brand damage)
4. **Report issues to regulators** (compliance risk)

### Decision Framework

| Scenario | Risk Level | Recommended Action |
|----------|-----------|---|
| 1+ failed txn, 3+ escalations, >0.8 risk | **CRITICAL** | Escalate to VP Customer Success immediately |
| 1+ failed txn, 3+ escalations, 0.6-0.8 risk | **HIGH** | Contact customer within 24 hours |
| 1+ failed txn, 2 escalations, >0.8 risk | **MEDIUM** | Schedule followup call within 48 hours |
| 0 failed txns, 3+ escalations, >0.8 risk | **MEDIUM** | Investigate support tickets for patterns |

## Extending the Case Study

This case study demonstrates the core pattern of semantic integration. You can extend it in several ways:

### Extension 1: Add Counterparties Domain

**Motivation**: Identify if transaction failures are concentrated with specific payment partners

**Steps**:
1. Create `domains/counterparties` directory
2. Define `fintech:Counterparty` RDF entities
3. Link counterparties to transactions via `fintech:transactionCounterparty`
4. Update federation query to include counterparty analysis
5. Create new query: `queries/counterparty-failure-analysis.sparql`

**Example Query**:
```sparql
SELECT ?customer ?counterparty ?failureCount
WHERE {
  SERVICE <http://accounts/sparql> {
    ?customer a fintech:Customer .
  }
  SERVICE <http://transactions/sparql> {
    ?txn fintech:transactionDebtor ?customer ;
         fintech:transactionStatus "failed" ;
         fintech:transactionCounterparty ?counterparty .
  }
  SERVICE <http://counterparties/sparql> {
    ?counterparty a fintech:Counterparty ;
                  fintech:counterpartyName ?cpName .
  }
}
GROUP BY ?customer ?counterparty
HAVING (COUNT(?txn) > 1)
```

### Extension 2: Add Market Data Domain

**Motivation**: Correlate churn risk with external market conditions

**Steps**:
1. Create `domains/market-data` domain
2. Define `fintech:MarketEvent` RDF entities
3. Link events to time periods and geographies
4. Update federation query to correlate churn with market volatility
5. Create new query: `queries/churn-vs-market-conditions.sparql`

### Extension 3: Real-Time Federated Queries

**Current State**: Batch queries executed on-demand

**Enhanced State**: Continuous monitoring queries

**Implementation**:
1. Deploy query execution as a Kubernetes CronJob
2. Execute churn query every 4 hours
3. Write results to a cache (Redis, DynamoDB)
4. Expose API for customer success team to query recent churn risks
5. Send Slack/email alerts for new critical cases

**Example**:
```bash
# Cron schedule: "0 */4 * * *" (every 4 hours)
arq --query churn-analysis-federated.sparql --results json | \
  jq '.results.bindings[] | select(.riskScore.value > 0.8)' | \
  redis-cli -x SET churn_risks
```

### Extension 4: Add Ontology Inference Rules

**Current State**: Static RDF data linked by shared URIs

**Enhanced State**: Inferred relationships via OWL rules

**Example Rules**:
```turtle
# Rule 1: If a customer has 2+ failed transactions, mark as "at_risk"
:hasFailedTransaction rdfs:subPropertyOf :hasRiskSignal .

# Rule 2: If a customer has 3+ support escalations, infer "dissatisfied"
:hasEscalation rdfs:subPropertyOf :hasDissatisfactionSignal .

# Rule 3: If customer has risk_score > 0.8 AND any risk signals, infer "churn_risk"
[] a owl:Class ;
   owl:equivalentClass [
     a owl:Class ;
     owl:onProperty fintech:riskScore ;
     owl:someValuesFrom [ owl:minInclusive "0.8"^^xsd:float ]
   ] .
```

### Extension 5: Add Query Caching & Performance Optimization

**Current State**: Federated queries execute all three SERVICE clauses every time

**Enhanced State**: Smart caching of stable data

**Implementation**:
1. Cache Accounts domain data (customer master data changes infrequently)
2. Cache Risk domain data (risk scores updated hourly)
3. Only fetch live Transactions data (changes constantly)
4. Implement 15-minute TTL cache for repeated queries

**Example Python Client**:
```python
import requests
import hashlib
import json
from datetime import datetime, timedelta
import redis

cache = redis.Redis(host='localhost', port=6379, db=0)

def cached_federated_query(query, ttl_seconds=900):
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    cache_key = f"sparql:{query_hash}"
    
    # Check cache
    cached_result = cache.get(cache_key)
    if cached_result:
        return json.loads(cached_result)
    
    # Execute query
    result = requests.get(
        'http://localhost:3030/accounts/sparql',
        params={'query': query}
    ).json()
    
    # Store in cache
    cache.setex(cache_key, ttl_seconds, json.dumps(result))
    return result
```

## Troubleshooting

Common issues and how to resolve them:

### Issue 1: Domain Endpoint Not Responding

**Error Message**:
```
SPARQL query execution failed: Connection timeout to http://localhost:3030/accounts/sparql
```

**Root Causes**:
- Domain container hasn't finished startup
- Domain port is not exposed
- Fuseki service crashed

**Resolution**:
```bash
# Check container status
docker ps | grep accounts

# View logs
docker logs accounts-fuseki

# Restart the container
docker restart accounts-fuseki

# Wait for health check to pass
docker exec accounts-fuseki curl http://localhost:3030/
```

### Issue 2: No Results Returned from Federated Query

**Error Message**:
```
Query executed successfully but returned 0 rows
```

**Root Causes**:
- Sample data not loaded
- RDF transformation didn't complete
- Date filters are too restrictive
- IRIs in different domains don't match

**Resolution**:
```bash
# Verify data was loaded in each domain
curl "http://localhost:3030/accounts/sparql?query=SELECT%20%28COUNT%28%3Fc%29%20AS%20%3Fcount%29%20WHERE%20%7B%3Fc%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FCustomer%3E%20%7D"

# Verify RDF transformation completed
docker logs accounts-transformer | grep "Transformation complete"

# Check if IRIs match across domains
# Accounts domain
curl "http://localhost:3030/accounts/sparql?query=SELECT%20%3Fc%20WHERE%20%7B%3Fc%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FCustomer%3E%7D"

# Transactions domain - should have same customer URIs
curl "http://localhost:3031/transactions/sparql?query=SELECT%20DISTINCT%20%3Fc%20WHERE%20%7B%3Ft%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FtransactionDebtor%3E%20%3Fc%20%7D"
```

### Issue 3: IRI Mismatches Between Domains

**Symptom**:
```
Some queries work (when linking within one domain)
Federated query returns no results (when linking across domains)
```

**Root Causes**:
- Transformation logic in Transactions domain mints its own customer IRIs instead of resolving them from Accounts
- Entity resolution rules not configured
- Namespace mismatch (one domain uses `/customer/` prefix, another uses `/customers/`)

**Resolution**:
```bash
# Verify IRI format is consistent
# Expected format: https://accounts.fintech.local/customer/cust_XXXXX

# Check transformation configuration
cat domains/transactions/config/entity-resolution.yaml

# Should have:
# entity_resolution:
#   customer:
#     source_endpoint: "http://accounts-domain:3030/accounts/sparql"
#     query: "SELECT ?customer_id ?iri WHERE { ?iri a fintech:Customer ; fintech:customerId ?customer_id }"

# Manually verify IRI resolution
curl "http://localhost:3030/accounts/sparql?query=SELECT%20%3Fc%20WHERE%20%7B%3Fc%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FCustomer%3E%20%3B%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FcustomerId%3E%20%22cust_12345%22%20%7D"
```

### Issue 4: SPARQL Syntax Errors in Query

**Error Message**:
```
Malformed query: Expected "}" at line 12, column 5
```

**Root Causes**:
- Typo in SPARQL syntax
- Missing semicolons or periods
- Unclosed braces or quotation marks

**Resolution**:
```bash
# Validate SPARQL syntax with rapper tool
rapper -c domains/federation/queries/churn-analysis-federated.sparql

# Or use online validator
# https://www.w3.org/2001/sw/DataFormats/N3/test/query.html

# Common issues to check:
# 1. All patterns end with . (period)
# 2. All variables start with ?
# 3. All URIs are <enclosed-in-brackets>
# 4. SERVICE blocks are properly paired { }
# 5. PREFIX declarations before WHERE clause
```

### Issue 5: Slow Query Execution

**Symptom**:
```
Query takes >30 seconds to return results
```

**Root Causes**:
- One domain endpoint is responding slowly
- Network latency between domains
- Query is not pushing filters to remote endpoints
- Cartesian product caused by missing join condition

**Resolution**:
```bash
# Optimize by pushing filters into SERVICE clauses
# BEFORE:
SERVICE <http://localhost:3030/transactions/sparql> {
  ?txn fintech:transactionDebtor ?customer ;
       fintech:transactionStatus "failed" ;
       fintech:transactionDate ?txnDate .
  # Filter applied AFTER network fetch
}

# AFTER:
SERVICE <http://localhost:3030/transactions/sparql> {
  ?txn fintech:transactionDebtor ?customer ;
       fintech:transactionStatus "failed" ;
       fintech:transactionDate ?txnDate .
  FILTER (?txnDate >= "2026-04-30"^^xsd:dateTime)  # Filter applied AT endpoint
}

# Check individual endpoint performance
time curl "http://localhost:3030/accounts/sparql?query=SELECT%20%28COUNT%28%3Fc%29%20AS%20%3Fcount%29%20WHERE%20%7B%3Fc%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FCustomer%3E%7D"

time curl "http://localhost:3031/transactions/sparql?query=SELECT%20%28COUNT%28%3Ft%29%20AS%20%3Fcount%29%20WHERE%20%7B%3Ft%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FTransaction%3E%7D"

time curl "http://localhost:3032/risk/sparql?query=SELECT%20%28COUNT%28%3Fr%29%20AS%20%3Fcount%29%20WHERE%20%7B%3Fr%20a%20%3Chttp%3A%2F%2Fchakracommerce.com%2Fontology%2Ffintech%2FRiskProfile%3E%7D"

# Identify slowest endpoint and investigate its logs
```

---

## Summary

This case study demonstrates a production-ready approach to cross-domain data integration in fintech:

- **Three autonomous domains** own their data and SPARQL endpoints
- **No centralized database** or transformation layer
- **SPARQL Federation** enables queries that span all domains
- **Shared URI naming** enables entity linking across domains
- **Business logic** (churn detection) is expressed in a single federated query
- **Results drive action** (customer retention outreach)

The architecture scales to more domains, more complex queries, and more sophisticated business logic while maintaining domain autonomy and data governance.
