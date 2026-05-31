# Fintech Semantic Integration: Shift-Left Semantics

## Overview

A **production-grade semantic data mesh implementation** demonstrating shift-left architecture where **domain teams own their RDF generation** instead of relying on a centralized semantic layer.

**Key Achievement:** 3 independent domains (Accounts, Transactions, Risk/Compliance) generate their own RDF, run their own SPARQL endpoints, and collaborate via federated queries—with zero centralized semantic bottleneck.

---

## Architecture

### Traditional Approach (Centralized Semantic Layer)
```
Domain Data → Central Semantic Team → Central RDF Layer → Federated Query
                                    ↑ Bottleneck
```

### Shift-Left Approach (Domain-Owned RDF)
```
Accounts Data ────→ Accounts RDF + SPARQL (port 3030) ─┐
Transactions Data ──→ Transactions RDF + SPARQL (3031) ├→ Federated Query
Risk Data ─────────→ Risk RDF + SPARQL (port 3032) ───┘
```

No central team. No semantic bottleneck. Each domain owns its semantics.

---

## Four Phases: Complete Implementation

### Phase 1: Accounts Domain (Customer & Account RDF)

**Responsibility:** Customer entity identity and account management

**Deliverables:**
- Customer + Account RDF entities with deterministic IRI minting
- IRI formula: `hash(email + kyc_id)` → consistent customer identity
- PostgreSQL + Jena Fuseki on port 3030
- 46 passing tests (unit + integration)
- Production-ready infrastructure

**Key Innovation:** Customer IRIs are minted deterministically, so other domains can resolve the same customer without a central ID service.

### Phase 2: Transactions Domain (Transaction & Counterparty RDF)

**Responsibility:** Transaction events and counterparty management

**Deliverables:**
- Transaction + Counterparty RDF entities
- Cross-domain customer linking via `fintech:transactionDebtor` property
- Uses Accounts domain IRI minting formula to resolve customers
- PostgreSQL + Jena Fuseki on port 3031
- 44 passing tests (unit + integration)
- Sample transaction data with edge cases

**Key Innovation:** Transactions domain links to customers using the same deterministic IRI formula—no central service, pure math.

### Phase 3: Risk/Compliance Domain (RiskProfile RDF)

**Responsibility:** Risk assessment and compliance verification

**Deliverables:**
- RiskProfile RDF entities (risk scores, compliance status, KYC status)
- Cross-domain customer linking via `fintech:forCustomer` property
- PostgreSQL + Jena Fuseki on port 3032
- 53 passing tests (unit + integration)
- Complete documentation with risk methodology

**Key Innovation:** Risk domain enriches customer data without owning or modifying customer entities.

### Phase 4: Federated Queries & Case Study

**Responsibility:** Cross-domain analysis and documentation

**Deliverables:**
1. **Federated Query Client** (`federated-query-client.py`)
   - Python library for executing queries across domains
   - Handles SERVICE {} federation syntax
   - Result formatting and error handling

2. **Churn Analysis Case Study** (Real-world 3-domain query)
   - Business question: Find customers with failed payments AND high risk scores
   - SPARQL query spanning all 3 domains
   - Executable script with CLI options

3. **Federation Guide** (`federation-guide.md`)
   - Complete tutorial on federated SPARQL
   - Step-by-step query writing guide
   - 5 common patterns with examples
   - Performance tips and troubleshooting

4. **Blog Post: "Shift-Left Semantics"** (`BLOG-SHIFT-LEFT-SEMANTICS.md`)
   - Technical deep-dive on domain-owned semantics
   - Why centralized semantic layers fail
   - How shift-left solves the problem
   - Getting-started guide

---

## Technical Highlights

### Deterministic IRI Minting (No Central Service)

Instead of calling an ID service:
```python
# Accounts domain mints
customer_iri = "https://chakracommerce.com/customer#" + hash(email + kyc_id)

# Transactions domain uses same formula to resolve
customer_iri = resolve_customer_iri(email, kyc_id)  # Returns same IRI!
```

### Cross-Domain Linking via Federated SPARQL

```sparql
SELECT ?customer ?name ?riskScore ?failedTxnCount
WHERE {
  SERVICE <http://accounts:3030/accounts/sparql> {
    ?customer fintech:customerName ?name
  }
  SERVICE <http://transactions:3031/transactions/sparql> {
    ?txn fintech:transactionDebtor ?customer;
         fintech:transactionStatus "failed"
  }
  SERVICE <http://risk:3032/risk_compliance/sparql> {
    ?risk fintech:forCustomer ?customer;
          fintech:riskScore ?riskScore
    FILTER (?riskScore > 0.8)
  }
}
GROUP BY ?customer ?name ?riskScore
HAVING (COUNT(?txn) >= 1)
ORDER BY DESC(?riskScore)
```

### Shared Ontology Contract (Not Centralized Implementation)

```turtle
# All domains reference these
fintech:Customer a owl:Class
fintech:Account a owl:Class
fintech:Transaction a owl:Class
fintech:forCustomer a rdf:Property
fintech:transactionDebtor a rdf:Property

# Each domain extends with its own properties
fintech:accountBalance a rdf:Property  # Accounts owns this
fintech:transactionStatus a rdf:Property  # Transactions owns this
fintech:riskScore a rdf:Property  # Risk owns this
```

---

## Test Coverage

**Total: 143 passing tests**

| Component | Unit Tests | Integration Tests | Total |
|-----------|------------|-------------------|-------|
| Accounts Domain | 46 | — | 46 |
| Transactions Domain | 34 | 10 | 44 |
| Risk Domain | 40 | 13 | 53 |
| **Total** | **120** | **23** | **143** |

### What's Tested

- **IRI Determinism:** Same input → Same IRI (case-insensitive, repeatable)
- **RDF Generation:** Correct triples with proper ontology types
- **Cross-Domain Linking:** IRIs match across domains via shared formula
- **SPARQL Queries:** Federation syntax works, results join correctly
- **Metadata:** sourceSystem and sourceIngestionTime on all triples
- **Error Handling:** Missing data, endpoint failures, timeout handling

---

## File Structure

```
chakraview-fintech-data-mesh/
├── domains/
│   ├── accounts/
│   │   ├── iri-minting-rules.yaml
│   │   ├── ontology-extensions.ttl
│   │   ├── src/main/python/semantic/
│   │   │   ├── iri_resolver.py
│   │   │   ├── silver_to_rdf.py
│   │   │   └── tests/
│   │   ├── config/
│   │   │   ├── fuseki-config.ttl
│   │   │   └── jena-tdb2.properties
│   │   ├── docker-compose.yml
│   │   └── README.md
│   ├── transactions/
│   │   ├── ... (same structure)
│   │   └── README.md
│   └── risk-compliance/
│       ├── ... (same structure)
│       └── README.md
│
└── docs/case-study/fintech-semantic-integration/
    ├── shared-ontology.ttl
    ├── federated-query-client.py
    ├── churn-analysis-federated.sparql
    ├── run-churn-analysis.py
    ├── federation-guide.md
    ├── BLOG-SHIFT-LEFT-SEMANTICS.md
    └── case-study-guide.md
```

---

## Key Metrics

| Metric | Value |
|--------|-------|
| **Domains** | 3 (Accounts, Transactions, Risk) |
| **Passing Tests** | 143 |
| **SPARQL Endpoints** | 3 (ports 3030, 3031, 3032) |
| **Lines of Code** | 6,000+ |
| **Lines of Documentation** | 5,000+ |
| **Production-Ready** | ✓ Yes |

---

## Running the System

### 1. Start All Domains

```bash
# Accounts domain
cd domains/accounts && docker-compose up -d

# Transactions domain
cd domains/transactions && docker-compose up -d

# Risk/Compliance domain
cd domains/risk-compliance && docker-compose up -d
```

### 2. Verify SPARQL Endpoints

```bash
# Each domain exposes a SPARQL endpoint
curl http://localhost:3030/accounts/sparql
curl http://localhost:3031/transactions/sparql
curl http://localhost:3032/risk_compliance/sparql
```

### 3. Run Churn Analysis Query

```bash
cd docs/case-study/fintech-semantic-integration
python run-churn-analysis.py --format table
```

---

## Key Benefits of Shift-Left

| Benefit | Traditional | Shift-Left |
|---------|-------------|-----------|
| **Ownership** | Central team | Domain team |
| **Bottleneck** | Semantic layer | None |
| **Query Time** | Weeks | Hours |
| **Scaling** | Central hiring | Automatic |
| **Debugging** | Central team | Domain expert |
| **Flexibility** | Slow (committee) | Fast (domain) |

---

## Lessons Learned

### 1. Determinism is Everything

Without deterministic IRI minting, entities can't be resolved across domains. Publish the formula in version-controlled YAML. Make it part of the ontology contract.

### 2. Shared Ontology ≠ Centralized Implementation

All domains reference the same entity types, but each implements its own RDF generation. The shared ontology is a contract, not a mandate.

### 3. SPARQL Federation Has Scale Limits

Works great for <1M triples per domain with early filtering. For massive datasets, add a hybrid layer (federation for exploration, materialized views for production).

### 4. Metadata is Critical

Every triple should carry `sourceSystem` and `sourceIngestionTime`. Makes debugging and lineage tracking trivial.

---

## References

- **Implementation:** [GitHub Repository](https://github.com/naren-chakraview/chakraview-fintech-data-mesh)
- **Federated Queries:** [SPARQL 1.1 Federation Spec](https://www.w3.org/TR/sparql11-federated-query/)
- **RDF Concepts:** [W3C RDF](https://www.w3.org/TR/rdf-concepts/)
- **Data Mesh:** [Zhamak Dehghani's Article](https://martinfowler.com/articles/data-mesh.html)

---

## Getting Started

1. Clone the repository
2. Read [Domain-Driven Semantic Architecture](./case-study-guide.md)
3. Follow [Federation Guide](./federation-guide.md)
4. Run the [Churn Analysis](./churn-analysis-federated.sparql) example
5. Read [Shift-Left Semantics Blog Post](./BLOG-SHIFT-LEFT-SEMANTICS.md)

---

**Status:** Production-ready reference implementation
**Last Updated:** May 2026
**Maintainer:** Naren Chakraview
