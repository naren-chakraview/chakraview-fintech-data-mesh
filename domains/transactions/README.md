# Transactions Domain

The Transactions domain owns real-time transaction events, settlement records, and clearing status for all payment activity. This is the highest-volume, lowest-latency domain in the data mesh. The semantic layer processes transactions and counterparties, generating RDF triples with cross-domain customer linking to the Accounts domain.

## Data Products

- **transaction-feed** — Real-time transaction events + settlement status
  - Tables: `raw_transactions`, `settlement_status`
  - Freshness: 5 minutes
  - Consumers: fraud detection, settlement reconciliation, compliance
  - RDF Endpoint: `http://localhost:3031/transactions/sparql` (semantic layer)

## Architecture

### Ingest Pipeline

```
Kafka: transactions-raw
  ↓ [Spark Structured Streaming, 5-min batches]
  ↓ Schema validation (Avro v2.1)
  ↓ Deduplication (Kafka offset tracking)
  ↓ Error handling (DLQ for failures)
Iceberg: transactions.raw_transactions (Silver tables)
  ↓ [RDF transformation pipeline]
  ↓ IRI minting (Transaction, Counterparty entities)
  ↓ Cross-domain customer resolution (link to Accounts domain IRIs)
  ↓ RDF triple generation
Jena Fuseki: TDB2 store (semantic layer)
  ↓ [SPARQL query endpoint]
```

### Semantic Layer Architecture

The Transactions domain semantic layer implements a three-stage transformation pipeline:

1. **Silver Tables (Iceberg)**: Normalized transaction and counterparty data from Kafka CDC
2. **IRI Minting**: Deterministic generation of RDF entity identifiers
   - **Transaction IRIs**: Based on globally unique `transaction_id`
   - **Counterparty IRIs**: Based on globally unique `counterparty_id`
   - **Customer IRIs**: Resolved from Accounts domain using cross-domain resolver
3. **RDF Generation**: Transformation to RDF triples with full semantic linking

#### Cross-Domain Customer Resolution

The Transactions domain does NOT own Customer entities—those are owned by the Accounts domain. Instead:
- Transaction records contain `customer_email` and `customer_kyc_id`
- The `CrossDomainResolver` applies the same normalization and hashing algorithm as Accounts domain
- This guarantees that transaction-customer links resolve to the same Customer IRI minted by Accounts
- Example: A transaction's debtor links to `https://chakracommerce.com/customer#a1b2c3d4`, the same IRI minted by Accounts for that customer

### Schemas

- **Avro** (Kafka): `schemas/avro/transaction-v2.1.avsc`
- **Iceberg** (Lake): `schemas/iceberg/raw_transactions.schema`, `settlement_status.schema`
- **RDF** (Semantic): `ontology-extensions.ttl` (Transaction, Counterparty, and cross-domain properties)

### Ingest Job

- **File**: `ingest/ingest_job.py`
- **Trigger**: Continuous Spark Structured Streaming
- **SLA**: 5-minute freshness, 99.9% availability

## File Structure

```
domains/transactions/
├── README.md                            # This file
├── requirements.txt                     # Python dependencies
├── docker-compose.yml                   # Services: PostgreSQL, Jena Fuseki
├── .env.example                         # Environment variables template
├── .env                                 # Local environment configuration
│
├── iri-minting-rules.yaml               # IRI minting specifications
├── ontology-extensions.ttl              # RDF schema extensions (fintech ontology)
│
├── ingest/
│   └── ingest_job.py                   # Spark ingest pipeline
│
├── schemas/
│   ├── avro/
│   │   └── transaction-v2.1.avsc       # Avro schema for Kafka
│   └── iceberg/
│       └── schemas.py                   # Iceberg table schema definitions
│
├── src/main/python/semantic/
│   ├── iri_resolver.py                 # Mint Transaction & Counterparty IRIs
│   ├── cross_domain_resolver.py        # Resolve Customer IRIs from Accounts domain
│   ├── silver_to_rdf.py                # Transform Silver tables to RDF
│   ├── rdf_writer.py                   # Write RDF to Jena Fuseki
│   └── tests/
│       ├── test_iri_resolver.py        # Unit tests for IRI minting
│       ├── test_cross_domain_resolver.py # Unit tests for cross-domain resolution
│       ├── test_silver_to_rdf.py       # Unit tests for RDF transformation
│       └── shared-ontology-test.ttl    # Test ontology fixture
│
├── tests/
│   └── test_integration_e2e.py         # End-to-end integration tests
│
├── config/
│   ├── fuseki-config.ttl               # Jena Fuseki RDF store configuration
│   └── jena-tdb2.properties            # TDB2 backend settings
│
├── data-products/
│   └── transaction-feed.yaml           # Data product specification
│
└── queries/
    ├── transaction-by-account.sql      # Query: transactions by account
    ├── settlement-reconciliation.sql    # Query: settlement status reconciliation
    └── fraud-scoring-join.sql          # Query: fraud detection data join
```

## Getting Started

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs the core Python packages needed for semantic transformation:
- `rdflib` - RDF triple manipulation and SPARQL
- `pandas` - Data transformation
- Plus Spark and PostgreSQL driver dependencies

### 2. Configure Environment

```bash
cp .env.example .env
# Adjust values if needed (default ports are 5432 for PostgreSQL, 3031 for Jena)
```

Environment variables include:
- PostgreSQL connection settings (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`)
- Jena Fuseki settings (`JENA_DATASET`, `JENA_PORT`)
- Path to shared ontology file (`SHARED_ONTOLOGY_PATH`)

### 3. Start Services

```bash
docker-compose up -d
```

This starts:
- **PostgreSQL** (port 5432): Stores Silver tables and metadata
- **Jena Fuseki** (port 3031): Hosts RDF triple store with SPARQL endpoint

### 4. Verify Services

Check PostgreSQL:
```bash
docker-compose exec postgres psql -U transactions_user -d transactions_db -c "SELECT 1;"
```

Check Jena Fuseki:
```bash
curl -s http://localhost:3031/ | head -20
```

Check SPARQL endpoint is accessible:
```bash
curl -s "http://localhost:3031/transactions/sparql?query=SELECT%20*%20%7B%7D%20LIMIT%201" | jq .
```

### 5. Load Sample Data (Optional)

```bash
# Create sample transaction records
docker-compose exec postgres psql -U transactions_user -d transactions_db < data/sample-transactions.sql
```

### 6. Run Unit Tests

```bash
pytest src/main/python/semantic/tests/ -v
```

Expected output:
```
test_iri_resolver.py::TestIriResolver::test_mint_transaction_iri_deterministic PASSED
test_iri_resolver.py::TestIriResolver::test_mint_transaction_iri_case_insensitive PASSED
test_cross_domain_resolver.py::TestCrossDomainResolver::test_resolve_customer_iri_deterministic PASSED
...
===== 12 passed in 0.45s =====
```

### 7. Run Integration Tests

```bash
pytest tests/test_integration_e2e.py -v
```

Expected output shows:
- RDF transformation from Silver tables
- SPARQL query execution
- Cross-domain customer linking verification
- All tests passing

## IRI Minting Rules

The Transactions domain mints IRIs deterministically using the `iri-minting-rules.yaml` specification.

### Transaction IRIs

**Key Field**: `transaction_id`  
**Algorithm**: Direct identity-based (no hashing)  
**Format**: `https://chakracommerce.com/transaction#{id}`

**Why**: Transaction IDs are globally unique in the source system. No normalization is needed.

**Example**:
- Input: `txn_001`
- Output: `https://chakracommerce.com/transaction#txn_001`

**Determinism**: Same transaction ID always produces the same IRI (idempotent).

### Counterparty IRIs

**Key Field**: `counterparty_id`  
**Algorithm**: Direct identity-based (no hashing)  
**Format**: `https://chakracommerce.com/counterparty#{id}`

**Why**: Counterparty IDs are globally unique. Examples: `stripe`, `paypal`, `bank_acme`, `merchant_xyz`.

**Example**:
- Input: `stripe`
- Output: `https://chakracommerce.com/counterparty#stripe`

**Determinism**: Same counterparty ID always produces the same IRI.

### Cross-Domain Customer Resolution

**Key Fields**: `customer_email`, `customer_kyc_id`  
**Algorithm**: SHA-256 hashing (same as Accounts domain)  
**Format**: `https://chakracommerce.com/customer#{hash}`

**Why**: Customers are owned by the Accounts domain. Transactions must reference the same Customer IRIs minted by Accounts to enable deduplication.

**Process**:
1. Normalize: Lowercase and trim both email and KYC ID
2. Concatenate: `{email}|{kyc_id}`
3. Hash: SHA-256 of concatenated string
4. Truncate: First 8 characters of hex digest
5. Format: `https://chakracommerce.com/customer#{hash}`

**Example**:
- Input: email = `JOHN@ACME.COM`, kyc_id = `KYC_123`
- Normalize: `john@acme.com`, `kyc_123`
- Concatenate: `john@acme.com|kyc_123`
- Hash: `a1b2c3d4f5e6...` (SHA-256)
- Output: `https://chakracommerce.com/customer#a1b2c3d4`

**Critical**: This MUST match the Accounts domain IRI exactly for entity deduplication to work across domains.

## RDF Schema

The Transactions domain defines RDF entities and properties in `ontology-extensions.ttl`.

### Entity Types

**fintech:Transaction**  
Represents a payment transaction. Key properties:

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `fintech:transactionId` | xsd:string | Transaction identifier | `txn_001` |
| `fintech:transactionAmount` | xsd:decimal | Amount in base currency | `2500.00` |
| `fintech:transactionStatus` | xsd:string | Status (executed, failed, pending, cancelled) | `executed` |
| `fintech:transactionDate` | xsd:dateTime | When transaction occurred | `2026-05-30T14:23:15Z` |
| `fintech:transactionDebtor` | fintech:Customer | Payer (references Accounts domain customer IRI) | `https://chakracommerce.com/customer#a1b2c3d4` |
| `fintech:transactionCreditor` | fintech:Counterparty | Receiver (counterparty) | `https://chakracommerce.com/counterparty#stripe` |

**fintech:Counterparty**  
Represents a payment processor, merchant, or other counterparty. Key properties:

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `fintech:counterpartyId` | xsd:string | Counterparty identifier | `stripe` |
| `fintech:counterpartyName` | xsd:string | Human-readable name | `Stripe Inc.` |
| `fintech:counterpartyType` | xsd:string | Type (processor, merchant, bank, exchange, etc.) | `processor` |

### Metadata Properties

All RDF entities include source system metadata:
- `sourceSystem` - Origin system (e.g., `payments-system-v2`)
- `sourceIngestionTime` - When data was loaded

### Full RDF Schema

For complete ontology details including class definitions, property domains/ranges, and shared properties, see:
- `ontology-extensions.ttl` (Transactions domain-specific definitions)
- `../../docs/case-study/fintech-semantic-integration/shared-ontology.ttl` (Shared fintech ontology)

## Cross-Domain Integration

The Transactions domain integrates with the Accounts domain through deterministic customer IRI resolution. This enables entity deduplication and federated SPARQL queries.

### How Cross-Domain Resolution Works

1. **Transactions domain** receives transaction records with `customer_email` and `customer_kyc_id`
2. **CrossDomainResolver** applies the same normalization and hashing algorithm as Accounts domain
3. Result is a Customer IRI that matches what Accounts domain minted
4. Transaction is linked via `fintech:transactionDebtor` property
5. Queries can now traverse from transaction → customer (from Accounts domain)

### Code Example: Using CrossDomainResolver

```python
from semantic.cross_domain_resolver import CrossDomainResolver

# Create resolver
resolver = CrossDomainResolver()

# Resolve customer IRI from transaction data
customer_iri = resolver.resolve_customer_iri(
    customer_email="john@acme.com",
    customer_kyc_id="kyc_123"
)

print(customer_iri)
# Output: https://chakracommerce.com/customer#a1b2c3d4
```

### Cross-Domain SPARQL Federation

Query transactions with customer data from Accounts domain using SPARQL SERVICE clause:

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
PREFIX cust: <https://chakracommerce.com/ontology/customer/>

SELECT ?transaction ?customer ?email ?transactionAmount
WHERE {
  # Query transactions in Transactions domain
  ?transaction a fintech:Transaction ;
               fintech:transactionAmount ?transactionAmount ;
               fintech:transactionDebtor ?customerIri .
  
  # Federated query to Accounts domain for customer details
  SERVICE <http://localhost:3032/accounts/sparql> {
    ?customerIri cust:email ?email ;
                 cust:name ?name .
  }
}
LIMIT 10
```

### Example: Find Transactions for a Customer

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT ?transaction ?amount ?status ?date
WHERE {
  ?transaction a fintech:Transaction ;
               fintech:transactionDebtor <https://chakracommerce.com/customer#a1b2c3d4> ;
               fintech:transactionAmount ?amount ;
               fintech:transactionStatus ?status ;
               fintech:transactionDate ?date .
}
ORDER BY DESC(?date)
```

This query finds all transactions linked to a specific customer IRI (resolved from email + KYC ID).

## Running Tests

### Unit Tests

Unit tests verify the core semantic transformation components:

```bash
pytest src/main/python/semantic/tests/ -v
```

**Test Coverage**:

- **test_iri_resolver.py** (11 tests)
  - IRI determinism (same ID → same IRI)
  - Case insensitivity (TXN_001 = txn_001)
  - Format correctness
  - Whitespace normalization
  - Different IDs produce different IRIs
  - Custom base URL support

- **test_cross_domain_resolver.py** (8 tests)
  - Customer IRI resolution determinism
  - Matching Accounts domain format
  - Case insensitivity
  - Whitespace normalization
  - Custom base URL support

- **test_silver_to_rdf.py** (6 tests)
  - Silver table transformation to RDF
  - Triple count validation
  - Cross-domain customer linking
  - Metadata annotation
  - SPARQL query execution on generated RDF

### Integration Tests

End-to-end tests verify the complete pipeline:

```bash
pytest tests/test_integration_e2e.py -v
```

**Test Coverage**:
- Load sample Silver table data (3+ transactions)
- Transform to RDF triples
- Verify cross-domain customer IRI linking
- Execute SPARQL queries on generated RDF
- Validate metadata tagging and ingestion timestamps
- Check all RDF triples are well-formed

### Run All Tests

```bash
pytest src/main/python/semantic/tests/ tests/ -v
```

Expected output: **25+ tests passing** with details on RDF transformation, IRI minting, and cross-domain resolution.

### Test with Coverage

```bash
pytest src/main/python/semantic/tests/ tests/ --cov=src/main/python/semantic --cov-report=html
```

View coverage report in `htmlcov/index.html`.

## SPARQL Endpoint

The Transactions domain exposes a SPARQL endpoint via Jena Fuseki for querying RDF triples.

### Connection Details

- **URL**: `http://localhost:3031/transactions/sparql` (default)
- **Available Endpoints**:
  - `/query` - SPARQL SELECT queries
  - `/update` - SPARQL INSERT/DELETE updates
  - `/gsp-r` - Graph Store Protocol read
  - `/gsp-rw` - Graph Store Protocol read/write

### Health Check

```bash
curl -s "http://localhost:3031/transactions/sparql?query=SELECT%20*%20%7B%7D%20LIMIT%201"
```

### Example: Count All Transactions

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT (COUNT(?transaction) AS ?count)
WHERE {
  ?transaction a fintech:Transaction .
}
```

Query via curl:
```bash
curl -s "http://localhost:3031/transactions/sparql" \
  --data-urlencode 'query=PREFIX fintech: <https://chakracommerce.com/ontology/fintech/> SELECT (COUNT(?transaction) AS ?count) WHERE { ?transaction a fintech:Transaction . }'
```

### Example: Find Transactions for a Customer

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT ?transaction ?amount ?status ?date
WHERE {
  ?transaction a fintech:Transaction ;
               fintech:transactionDebtor <https://chakracommerce.com/customer#a1b2c3d4> ;
               fintech:transactionAmount ?amount ;
               fintech:transactionStatus ?status ;
               fintech:transactionDate ?date .
}
ORDER BY DESC(?date)
LIMIT 20
```

Replace `customer#a1b2c3d4` with the actual customer IRI (resolved using CrossDomainResolver).

### Example: List All Counterparties

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT ?counterparty ?name ?type
WHERE {
  ?counterparty a fintech:Counterparty ;
                fintech:counterpartyName ?name ;
                fintech:counterpartyType ?type .
}
```

### Using Python with RDFLib

```python
from rdflib import Graph, Namespace

g = Graph()
g.parse("http://localhost:3031/transactions/sparql", format="sparql")

FINTECH = Namespace('https://chakracommerce.com/ontology/fintech/')

# Query all transactions
for transaction in g.subjects(predicate=RDF.type, object=FINTECH.Transaction):
    print(f"Transaction: {transaction}")
```

## Development

### Modifying IRI Minting Rules

1. **Edit** `iri-minting-rules.yaml` with new rules or algorithms
2. **Update** corresponding methods in `src/main/python/semantic/iri_resolver.py`
3. **Run tests** to verify determinism: `pytest src/main/python/semantic/tests/test_iri_resolver.py -v`
4. **Regenerate RDF** with new rules: `python -m semantic.silver_to_rdf`

### Extending RDF Schema

1. **Add properties** to `ontology-extensions.ttl` following Turtle format
2. **Update transformation code** in `src/main/python/semantic/silver_to_rdf.py` to populate new properties
3. **Add test cases** in `src/main/python/semantic/tests/test_silver_to_rdf.py`
4. **Run tests** to validate schema consistency

Example: Adding a new property `fintech:transactionFee`:

```turtle
# In ontology-extensions.ttl
fintech:transactionFee
  a rdf:Property ;
  rdfs:domain fintech:Transaction ;
  rdfs:range xsd:decimal ;
  rdfs:label "Fee" ;
  rdfs:comment "Transaction processing fee" ;
  fintech:owningDomain "transactions" .
```

Then update `silver_to_rdf.py`:
```python
if 'fee' in row and pd.notna(row['fee']):
    self.g.add((txn_iri, self.FINTECH.transactionFee,
               Literal(float(row['fee']), datatype=self.FINTECH.decimal)))
```

### Adding Test Cases

Unit tests in `src/main/python/semantic/tests/`:
```python
def test_new_feature(self):
    """Test: New feature works correctly."""
    result = feature_under_test()
    assert result == expected_value
```

Integration tests in `tests/test_integration_e2e.py`:
```python
def test_new_scenario(self, transformer, sample_data):
    """Test: New scenario in end-to-end pipeline."""
    graph = transformer.transform_transactions_to_rdf(sample_data)
    # Assertions about graph content
    assert len(list(graph.triples(...))) > 0
```

### Debugging

**View Docker logs**:
```bash
docker-compose logs -f postgres     # PostgreSQL logs
docker-compose logs -f jena-fuseki  # Jena Fuseki logs
```

**Run tests with verbose output**:
```bash
pytest src/main/python/semantic/tests/ -v -s
```

**Inspect RDF triples generated**:
```python
from rdflib import Graph
from semantic.silver_to_rdf import SilverToRdfTransformer

g = transformer.transform_transactions_to_rdf(df)
for s, p, o in g:
    print(f"{s} {p} {o}")
```

**Check SPARQL endpoint directly**:
```bash
curl -s "http://localhost:3031/transactions/sparql?query=SELECT%20*%20WHERE%20%7B%20%3Fs%20%3Fp%20%3Fo%20%7D%20LIMIT%205"
```

## Integration with Other Domains

### Accounts Domain (Customer Owner)

The **Accounts domain** owns the Customer entity and mints Customer IRIs. The Transactions domain:
- Does NOT mint Customer IRIs
- Uses `CrossDomainResolver` to deterministically derive the same Customer IRI
- Links transactions to customers via `fintech:transactionDebtor` property
- Allows queries to traverse from transaction → customer data

**Related**: See `../accounts/README.md` for Customer IRI minting rules.

### Risk/Compliance Domain (Consumer)

The **Risk domain** consumes transaction and customer data to:
- Score fraud risk per transaction
- Link to customer KYC status from Accounts domain
- Generate compliance alerts

Risk domain queries may use federated SPARQL (SERVICE clause) to:
- Query transactions in Transactions domain
- Join with customer data in Accounts domain

### Three-Domain Federation

Query across all three domains (Accounts, Transactions, Risk):

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
PREFIX cust: <https://chakracommerce.com/ontology/customer/>
PREFIX risk: <https://chakracommerce.com/ontology/risk/>

SELECT ?customer ?name ?email ?transactionAmount ?riskScore
WHERE {
  # Customer from Accounts domain
  SERVICE <http://localhost:3032/accounts/sparql> {
    ?customerIri cust:name ?name ; cust:email ?email .
  }
  
  # Transactions from Transactions domain
  ?transaction fintech:transactionDebtor ?customerIri ;
               fintech:transactionAmount ?transactionAmount .
  
  # Risk scores from Risk domain
  SERVICE <http://localhost:3033/risk/sparql> {
    ?riskAssessment risk:customer ?customerIri ;
                    risk:score ?riskScore .
  }
}
```

## Related Documentation

- **[Accounts Domain README](../accounts/README.md)** — Customer entity owner, IRI minting for customers
- **[Fintech Semantic Integration Case Study](../../docs/case-study/fintech-semantic-integration/case-study-guide.md)** — Overall semantic layer architecture, cross-domain patterns, federation examples
- **Shared Ontology** — `../../docs/case-study/fintech-semantic-integration/shared-ontology.ttl` (fintech ontology with all entity and property definitions)

## Query Examples

Reference queries for common scenarios:

- **By Account**: `queries/transaction-by-account.sql`
- **Settlement Reconciliation**: `queries/settlement-reconciliation.sql`
- **Fraud Scoring Input**: `queries/fraud-scoring-join.sql`

## Testing

- **Unit**: Schema validation, deduplication logic, IRI minting, cross-domain resolution
- **Integration**: Kafka → Iceberg → RDF pipeline, SPARQL queries, entity linking
- **Compliance**: PII masking, audit logging, retention

## Operational Runbooks

See `../../docs/domains/transactions/` for:
- Schema evolution process
- Troubleshooting ingest failures
- Compaction performance tuning
- SPARQL query optimization
