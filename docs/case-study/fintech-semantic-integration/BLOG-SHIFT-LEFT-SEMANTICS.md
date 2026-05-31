# Shift-Left Semantics: Domain Teams Own Their RDF

## The Problem With Centralized Semantic Layers

Data mesh architecture solved a critical problem: **decentralized ownership**. Instead of a monolithic data warehouse, each domain team owns its data products, runs its own pipelines, and serves its own consumers.

But semantic modeling—the layer that makes cross-domain queries possible—remained centralized.

A typical semantic integration looks like this:

```
Accounts Domain         Transactions Domain      Risk Domain
    ↓                        ↓                         ↓
[Silver Tables]          [Silver Tables]         [Silver Tables]
    ↓                        ↓                         ↓
    └──────────┬─────────────┴──────────┬────────────┘
               ↓
     [Central Semantic Batch Lakehouse]
     (Convert Silver → RDF)
            ↓
     [Semantic Query Layer]
            ↓
     [Federated SPARQL]
```

Who runs the "Semantic Batch Lakehouse"? A central team. Who decides the RDF schema? A central committee. Who debugs semantic issues? Central ops.

The result: **you've decentralized data ownership but recentralized semantic responsibility.**

This creates a bottleneck. Semantic work queues up behind central team priorities. Domains that want to expose their data semantically must ask permission and wait for slots. By the time the central team understands a domain's RDF needs, the domain team has iterated three times and lost context.

We solved this before, with microservices. The lesson: **push responsibility to the edge.**

## The Shift-Left Solution

What if **each domain generated its own RDF**?

```
Accounts Domain              Transactions Domain           Risk Domain
    ↓                             ↓                             ↓
[Silver Tables]             [Silver Tables]            [Silver Tables]
    ↓                             ↓                             ↓
[RDF Transform]            [RDF Transform]           [RDF Transform]
(Domain owns it)           (Domain owns it)           (Domain owns it)
    ↓                             ↓                             ↓
[Jena TDB2]               [Jena TDB2]                [Jena TDB2]
[SPARQL :3030]            [SPARQL :3031]             [SPARQL :3032]
    ↓                             ↓                             ↓
    └──────────┬─────────────┴──────────┬────────────┘
               ↓
         [Federated Query]
         (Consumer owns it)
```

No central semantic layer. Each domain:
- Generates its own RDF triples
- Mints its own IRIs (Internationalized Resource Identifiers)
- Runs its own SPARQL endpoint
- Takes full responsibility for semantic correctness

Domains collaborate through a **shared ontology contract**—think "OpenAPI for semantics"—but implementation is decentralized.

## Why This Works

### 1. Ownership Follows Data

In data mesh, the rule is simple: **the team that owns the data owns the data quality.**

Extend that rule: **the team that owns the data owns the semantics of that data.**

Accounts domain knows customers best. They should own Customer RDF entities.
Transactions domain knows transactions best. They should own Transaction RDF entities.

No central team has that deep context. Shifting semantic responsibility to the domain is not just faster—it's more correct.

### 2. IRI Minting at Source

Entity deduplication in semantic systems is hard. When you have customers in Salesforce, Stripe, and Postgres, which one is "the real" customer?

Centralized systems often introduce a "master ID service"—which becomes its own bottleneck.

Shift-left: **domains mint their own IRIs at ingestion time, using deterministic rules.**

Example: Accounts domain determines that a customer's IRI is built from `email + KYC_ID`, hashed deterministically:

```python
customer_iri = "https://chakracommerce.com/customer#" + hash(email + kyc_id)
```

This rule is **published in an ontology file**, and Transactions domain uses the same rule when resolving "which Account customer does this transaction belong to?"

No call to a central service. No ID lookup table. Just deterministic math at the domain level.

### 3. Cross-Domain Linking Without Centralization

Without a central service, how do domains link to each other?

**Via IRI matching.**

Transactions domain sees a transaction from `john@acme.com` with KYC ID `kyc_12345`. It wants to link that transaction to the customer entity from Accounts domain.

It runs the same IRI minting formula:
```python
customer_iri = "https://chakracommerce.com/customer#" + hash(email + kyc_id)
```

If Accounts domain minted the same IRI using the same formula, the IRIs match. **No central resolution needed. No lookup table. Just math.**

### 4. Semantic Responsibility is Local

Each domain team understands their own RDF schema deeply:

- **Accounts:** Knows how Customer and Account entities relate. Knows which properties are critical for identity.
- **Transactions:** Knows which entity types matter (Transaction, Counterparty). Knows how they link to customers.
- **Risk:** Knows RiskProfile semantics—what makes a customer "high risk," what fields are required for compliance.

When a domain modifies its semantics, the domain team is responsible for backward compatibility and validation. No central committee approving every change.

### 5. Consumers Own Cross-Domain Queries

In centralized systems, analysts ask the central team: "Can we join customer data with risk profiles?" The central team designs the join, documents it, provides a view.

Shift-left: **Consumers write their own federated SPARQL queries** across domain SPARQL endpoints.

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

Consumers choose which domains to query, at query time. If a new domain comes online, consumers can start querying it immediately—no central pipeline changes.

## The Fintech Data Mesh Case Study

We implemented this pattern for a fintech platform with three domains:

### Accounts Domain
- **Owns:** Customer, Account RDF entities
- **Runs:** PostgreSQL + Jena Fuseki on port 3030
- **Responsibility:** Customer identity (IRI minting), account properties, metadata

### Transactions Domain
- **Owns:** Transaction, Counterparty RDF entities
- **Runs:** PostgreSQL + Jena Fuseki on port 3031
- **Responsibility:** Cross-domain customer linking via fintech:transactionDebtor
- **Key trick:** Uses Accounts domain's IRI minting formula to resolve customers deterministically

### Risk/Compliance Domain
- **Owns:** RiskProfile RDF entities
- **Runs:** PostgreSQL + Jena Fuseki on port 3032
- **Responsibility:** Risk assessments, compliance status, KYC verification
- **Key trick:** Links to customer via fintech:forCustomer using Accounts domain IRIs

### Cross-Domain Query: Churn Analysis

Business question: "Find customers with failed payments AND high risk scores."

**No central pipeline.** Consumer writes a federated query:

```sparql
SELECT ?customer ?name ?riskScore (COUNT(?failedTxn) AS ?failureCount)
WHERE {
  SERVICE <http://accounts:3030/accounts/sparql> {
    ?customer fintech:customerName ?name .
  }
  SERVICE <http://transactions:3031/transactions/sparql> {
    ?txn fintech:transactionDebtor ?customer ;
         fintech:transactionStatus "failed" .
  }
  SERVICE <http://risk:3032/risk_compliance/sparql> {
    ?risk fintech:forCustomer ?customer ;
          fintech:riskScore ?riskScore .
    FILTER (?riskScore > 0.8)
  }
}
GROUP BY ?customer ?name ?riskScore
HAVING (COUNT(DISTINCT ?txn) >= 1)
```

Each domain answers its piece independently. Results are joined by the SPARQL federation engine. No data export. No central transform. No bottleneck.

## Key Architectural Decisions

### 1. RDF Storage: Jena TDB2 + Apache Iceberg

Each domain runs Jena TDB2 for SPARQL queries and Apache Iceberg for audit trails. This gives:
- **Fast SPARQL:** TDB2 is optimized for RDF triple queries
- **Audit trail:** Iceberg stores RDF as parquet for compliance/lineage
- **Decentralized:** Each domain manages its own infrastructure

### 2. IRI Format: Deterministic, Not Central

Instead of minting IRIs through a service, domains use a deterministic formula. Example:

```
Customer IRI = https://chakracommerce.com/customer#{hash(email + kyc_id)}
```

This is published in the **ontology file**, not hidden in code. Any domain can replicate it.

### 3. Shared Ontology: A Contract, Not a Mandate

All domains reference the same ontology for entity types and properties:

```turtle
fintech:Customer a owl:Class .
fintech:RiskProfile a owl:Class .
fintech:forCustomer a rdf:Property .
```

But domains extend the ontology for their own properties:

```turtle
# Accounts domain extensions
fintech:accountBalance a rdf:Property .

# Transactions domain extensions
fintech:transactionStatus a rdf:Property .

# Risk domain extensions
fintech:riskScore a rdf:Property .
```

The shared ontology is **negotiated** (domains agree on entity types), but **implementation is distributed** (each domain owns its properties).

### 4. Federated Queries: SPARQL 1.1 SERVICE

We use standard SPARQL 1.1 federation (`SERVICE {}` clauses). This is:
- **Portable:** Works with any SPARQL endpoint
- **Standardized:** No proprietary query language
- **Transparent:** Query shows which domains are involved

## Lessons Learned

### 1. Determinism is Key

IRI minting must be **deterministic and published**. If Accounts domain mints IRIs as `hash(email)` but Transactions domain tries to replicate it as `hash(email + kyc_id)`, they'll never match.

Solution: Document the IRI minting rules in version-controlled YAML. Make them part of the ontology contract.

### 2. Cross-Domain Linking Requires Shared Keys

Transactions domain needs to resolve "which customer is this transaction from?" If customer ID isn't available, link via email or phone number—but document which identifier is the canonical key.

In our case: `email + kyc_id` is the canonical customer key. All domains use this for linking.

### 3. SPARQL Federation Has Limits

Federation works great when:
- You have <1M triples per domain
- Queries filter early (push FILTER inside SERVICE blocks)
- You accept eventual consistency

Federation breaks down when:
- You need sub-second response times across domains
- You have massive datasets (>1B triples)
- You need ACID-level consistency

For true high-scale systems, you might add a **hybrid layer**—federated SPARQL for exploration, a materialized view for production queries.

### 4. Metadata is Critical

Every RDF triple should carry metadata:
- `sourceSystem`: Which domain created it? (risk_compliance, transactions, etc.)
- `sourceIngestionTime`: When was it ingested? (for auditing and lineage)

This makes debugging federation queries much easier. You can trace where a result came from.

## The Shift-Left Wins

Compared to centralized semantic layers:

| Dimension | Centralized | Shift-Left |
|-----------|------------|-----------|
| **Ownership** | Central team | Domain team |
| **Bottleneck** | Semantic layer | None |
| **Time to query** | Weeks (central design + impl) | Hours (consumer writes query) |
| **Scaling** | Central team hiring | Automatic (domains own it) |
| **Debugging** | Central team | Domain team (who knows data) |
| **Flexibility** | Committees decide schema | Domains evolve schema |
| **Cost** | Centralized infrastructure | Distributed endpoints |

The shift-left approach is faster, more scalable, and puts responsibility where it belongs: **with the teams that own the data.**

## Getting Started

If you want to implement shift-left semantics:

1. **Start with one domain.** Implement IRI minting and basic RDF transformation for one entity type. Prove the pattern works.

2. **Publish the ontology.** Write down the entity types, properties, and IRI minting rules in Turtle. Version it.

3. **Add a second domain.** Extend the ontology with new entity types. Implement cross-domain linking using the shared IRI formula. Run a federated query.

4. **Operationalize.** Set up monitoring, alerting, and runbooks for each domain's SPARQL endpoint.

5. **Document patterns.** Share example queries with consumers. Build a query template library.

See the [Federation Guide](./federation-guide.md) for detailed steps and examples.

## Conclusion

Semantic modeling doesn't need a central team. Like data meshes, semantic systems work better when **domain teams own their own semantics.**

By shifting semantic responsibility to the domain level, you get:
- **Faster queries:** No central bottleneck
- **Smarter semantics:** Domains encode their deep knowledge
- **Simpler architecture:** Standard SPARQL federation, no custom platforms
- **Better scaling:** Responsibility grows with domains, not with central team

The lesson from data mesh applies to semantics too: **push responsibility to the edge, and the system scales.**

---

## References

- **Original implementation:** [Chakraview Fintech Data Mesh](https://github.com/naren-chakraview/chakraview-fintech-data-mesh)
- **Federated queries:** [SPARQL 1.1 Federated Query spec](https://www.w3.org/TR/sparql11-federated-query/)
- **Data mesh:** [Zhamak Dehghani's original article](https://martinfowler.com/articles/data-mesh.html)
- **RDF/Semantics:** [W3C RDF Concepts](https://www.w3.org/TR/rdf-concepts/)
- **Case study:** [Fintech Churn Analysis Example](./churn-analysis-federated.sparql)
