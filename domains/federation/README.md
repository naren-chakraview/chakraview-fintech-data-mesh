# SPARQL Federation: Cross-Domain Semantic Queries

## Overview

This directory contains the domain registry and federated SPARQL query patterns used to implement cross-domain semantic integration. SPARQL Federation enables queries that span multiple SPARQL endpoints while maintaining domain autonomy and data ownership.

## What is SPARQL Federation?

SPARQL Federation is a mechanism defined in the [SPARQL 1.1 Specification](https://www.w3.org/TR/sparql11-federated-query/) that allows a SPARQL query to query multiple remote SPARQL endpoints simultaneously.

### The SERVICE {} Syntax

The `SERVICE` keyword enables queries to be sent to remote endpoints:

```sparql
SERVICE <http://endpoint-url/sparql> {
  # Pattern matching against the remote endpoint
  ?subject ?predicate ?object .
}
```

When a SPARQL query engine encounters a `SERVICE` clause:

1. It executes the pattern inside the braces against the specified remote endpoint
2. The remote endpoint returns bindings for the specified variables
3. These bindings are joined with bindings from other patterns in the WHERE clause
4. Results are filtered and aggregated according to the query logic

### Benefits for Domain-Driven Architecture

- **Domain Autonomy**: Each domain owns its own SPARQL endpoint and data model
- **Loose Coupling**: Domains don't need to share databases or be tightly integrated
- **Semantic Integration**: Entities are linked across domains via shared URIs (e.g., customer IDs)
- **Scalability**: Queries are distributed across multiple endpoints
- **Transparency**: Query logic is explicit and auditable

## Domain Registry

The `domain-registry.yaml` file serves as a service discovery mechanism. It defines:

1. **Domain Identity**: Name and description of each domain
2. **SPARQL Endpoint**: URL where the domain's SPARQL endpoint is accessible
3. **Owned Entities**: Types of RDF entities that the domain owns (e.g., Customer, Transaction)

### Current Domains

```yaml
accounts:
  - Manages Customer and Account entities
  - Endpoint: http://accounts-domain.internal:3030/accounts/sparql

transactions:
  - Manages Transaction and Counterparty entities
  - Endpoint: http://transactions-domain.internal:3030/transactions/sparql

risk-compliance:
  - Manages RiskProfile and compliance data
  - Endpoint: http://risk-domain.internal:3030/risk/sparql
```

## How to Query Across Domains

### Step 1: Identify Required Domains

Determine which domains own the entities you need:

- Looking for customer churn? You need: Accounts, Transactions, and Risk domains
- Looking for transaction anomalies? You need: Transactions and Risk domains
- Looking for regulatory compliance? You need: Risk/Compliance and Transactions domains

### Step 2: Write SERVICE Clauses

For each domain, create a `SERVICE` clause that queries that domain's endpoint:

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT ?customer ?amount
WHERE {
  # Query Accounts for customer info
  SERVICE <http://accounts-domain.internal:3030/accounts/sparql> {
    ?customer a fintech:Customer ;
              fintech:customerName ?name .
  }
  
  # Query Transactions for their transactions
  SERVICE <http://transactions-domain.internal:3030/transactions/sparql> {
    ?txn fintech:transactionDebtor ?customer ;
         fintech:transactionAmount ?amount .
  }
}
```

### Step 3: Use Shared Identifiers

The join across domains happens via shared variables. In the example above:
- `?customer` is bound in the Accounts domain SERVICE clause
- The same `?customer` variable is used in the Transactions domain SERVICE clause
- The query engine automatically joins results on matching `?customer` URIs

### Step 4: Apply Filters and Aggregations

Use standard SPARQL filters and aggregations to narrow results:

```sparql
WHERE {
  SERVICE <...> { ... }
  SERVICE <...> { ... }
  FILTER (?amount > 1000)
}
GROUP BY ?customer
HAVING (COUNT(?txn) > 5)
ORDER BY DESC(?amount)
```

## Example: Churn Analysis Query

The `queries/churn-analysis-federated.sparql` query demonstrates a real-world cross-domain scenario:

### Query Purpose

Identify high-risk customers with recent failed transactions who may be candidates for churn.

### Query Structure

```sparql
SELECT ?customer ?name ?ticketCount ?failedTxnCount ?riskScore
WHERE {
  # SERVICE 1: Get customer information from Accounts domain
  SERVICE <http://accounts-domain.internal:3030/accounts/sparql> {
    ?customer a fintech:Customer ;
              fintech:customerName ?name ;
              fintech:customerEmail ?email .
  }
  
  # SERVICE 2: Get recent failed transactions from Transactions domain
  SERVICE <http://transactions-domain.internal:3030/transactions/sparql> {
    ?transaction fintech:transactionDebtor ?customer ;
                 fintech:transactionStatus "failed" ;
                 fintech:transactionDate ?txnDate .
    FILTER (?txnDate > "2026-04-30"^^xsd:dateTime)
  }
  
  # SERVICE 3: Get risk scores from Risk/Compliance domain
  SERVICE <http://risk-domain.internal:3030/risk/sparql> {
    ?riskProfile fintech:forCustomer ?customer ;
                 fintech:riskScore ?riskScore .
    FILTER (?riskScore > 0.8)
  }
}
GROUP BY ?customer ?name ?riskScore
HAVING (COUNT(DISTINCT ?transaction) >= 1)
ORDER BY DESC(?riskScore)
```

### Line-by-Line Explanation

1. **Prefix declarations**: Define namespace shortcuts for entity types
2. **SELECT clause**: Specify which variables to return (customer ID, name, risk score)
3. **Accounts domain query**: 
   - Finds all customers (`?customer a fintech:Customer`)
   - Retrieves their name and email
4. **Transactions domain query**:
   - Finds transactions where the customer is the debtor
   - Filters for failed transactions
   - Filters for transactions after April 30, 2026
5. **Risk domain query**:
   - Finds the risk profile associated with each customer
   - Filters for high-risk scores (> 0.8)
6. **GROUP BY / HAVING / ORDER BY**:
   - Groups results by customer
   - Ensures at least 1 failed transaction
   - Sorts by risk score (highest first)

### Expected Result

A list of high-risk customers with:
- Recent transaction failures
- High compliance risk scores
- Names and email addresses for outreach

## Adding New Domains

### Step 1: Register the Domain

Add an entry to `domain-registry.yaml`:

```yaml
  new-domain:
    name: "New Domain Name"
    sparql_endpoint: "http://new-domain.internal:3030/new-domain/sparql"
    description: "Description of entities managed by this domain"
    owned_entities:
      - Entity1
      - Entity2
```

### Step 2: Define Shared Entities

Ensure the new domain uses the same ontology namespace (`https://chakracommerce.com/ontology/fintech/`) for shared entity types.

### Step 3: Write Integration Queries

Create new SPARQL files in `queries/` that incorporate the new domain:

```sparql
SERVICE <http://new-domain.internal:3030/new-domain/sparql> {
  ?entity a fintech:SharedEntityType ;
          fintech:property ?value .
}
```

### Step 4: Test the Query

1. Verify the remote endpoint is accessible
2. Run the query against a SPARQL query tool (e.g., Apache Jena Fuseki)
3. Validate results are as expected

### Step 5: Document the Query

Add a comment block explaining:
- What business question the query answers
- Which domains are queried and why
- Expected result structure

## Failure Scenarios and Resilience

### Scenario 1: Domain Endpoint Down

If a domain endpoint is unavailable:

```
SPARQL query execution fails with an error
No partial results are returned
The entire query fails atomically
```

**Mitigation**:
- Implement timeout handling in your query client
- Retry with exponential backoff
- Consider caching results from previous successful queries
- Use OPTIONAL SERVICE clauses for non-critical domains

Example with OPTIONAL:
```sparql
SERVICE <domain1-endpoint> { ... }
OPTIONAL { SERVICE <domain2-endpoint> { ... } }
```

### Scenario 2: Slow Endpoint

If one domain responds slowly:

```
The entire query is slow (as slow as the slowest component)
Network latency is magnified across multiple hops
```

**Mitigation**:
- Add timeout constraints to SPARQL queries
- Query endpoints in parallel (order-independent)
- Implement query result caching
- Consider pre-computing common federated queries

### Scenario 3: No Matching Results in One Domain

If a domain returns no results for a pattern:

```
The entire outer query returns no results
The pattern is treated as a failed join
```

**Mitigation**:
- Use OPTIONAL SERVICE clauses for optional data
- Provide default values with COALESCE
- Restructure queries to handle sparse data

## Best Practices

1. **Use SERVICE for Domain-Owned Data**: Only use SERVICE clauses for data that belongs to that domain
2. **Minimize Data Transfer**: Return only the variables you need in SELECT
3. **Push Filters Down**: Use FILTER inside SERVICE clauses to reduce network traffic
4. **Test Each Domain**: Verify each SERVICE clause works independently first
5. **Version Your Ontology**: Track changes to the shared fintech ontology
6. **Monitor Query Performance**: Log slow queries and endpoint response times
7. **Document Dependencies**: Clearly mark which domains each query depends on

## Tools and Infrastructure

### Local Testing

Use Apache Jena Fuseki to set up test SPARQL endpoints:

```bash
docker run -p 3030:3030 apache/jena-fuseki
```

### Query Validation

Validate SPARQL syntax with online validators:
- [SPARQL Query Validator](https://www.w3.org/2001/sw/DataFormats/N3/test/query.html)

### Production Deployment

In production, domains are deployed as containerized SPARQL services:
- Fuseki, AllegroGraph, GraphDB, or equivalent
- Service discovery via Kubernetes DNS or Consul
- Query execution distributed across replica endpoints

## Related Documentation

- [SPARQL 1.1 Federated Query Specification](https://www.w3.org/TR/sparql11-federated-query/)
- [Semantic Web Best Practices](https://www.w3.org/2001/sw/BestPractices/)
- [Domain-Driven Design in Fintech](../README.md)
