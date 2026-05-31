# Risk/Compliance Domain

The Risk/Compliance domain owns real-time fraud detection and regulatory compliance scoring for all customers. This domain performs continuous risk assessments, tracks KYC/AML verification status, and maintains compliance records. The semantic layer processes risk profiles and generates RDF triples with cross-domain customer linking to the Accounts domain.

## Data Products

- **risk-scores** — Fraud detection scores + KYC/AML verdicts
  - Tables: `fraud_scores`, `kyc_verdicts`
  - Freshness: 10 minutes
  - Consumers: real-time decision engines, compliance monitoring, regulatory reporting
  - Retention: 10 years (AML requirement)
  - RDF Endpoint: `http://localhost:3032/risk-compliance/sparql` (semantic layer)

## Architecture

### Ingest Pipeline

```
Fraud Detection System → Kafka: risk-events
  ↓ [Spark Structured Streaming, 10-min batches]
  ↓ Schema validation (Avro v1.0)
  ↓ Risk scoring computation (fraud flags, AML checks)
  ↓ Error handling (DLQ for failures)
Iceberg: risk_compliance.fraud_scores (Silver tables)
Iceberg: risk_compliance.kyc_verdicts (Silver tables)
  ↓ [RDF transformation pipeline]
  ↓ IRI minting (RiskProfile entities)
  ↓ Cross-domain customer resolution (link to Accounts domain IRIs)
  ↓ RDF triple generation
Jena Fuseki: TDB2 store (semantic layer)
  ↓ [SPARQL query endpoint]
```

### Semantic Layer Architecture

The Risk/Compliance domain semantic layer implements a three-stage transformation pipeline:

1. **Silver Tables (Iceberg)**: Normalized risk assessment and compliance data
2. **IRI Minting**: Deterministic generation of RDF entity identifiers
   - **RiskProfile IRIs**: Based on globally unique `risk_id`
   - **Customer IRIs**: Resolved from Accounts domain using cross-domain resolver
3. **RDF Generation**: Transformation to RDF triples with full semantic linking

#### Cross-Domain Customer Resolution

The Risk/Compliance domain does NOT own Customer entities—those are owned by the Accounts domain. Instead:
- Risk records contain `customer_email` and `customer_kyc_id`
- The `CrossDomainResolver` applies the same normalization and hashing algorithm as Accounts domain
- This guarantees that risk-customer links resolve to the same Customer IRI minted by Accounts
- Example: A risk profile's customer links to `https://chakracommerce.com/customer#a1b2c3d4`, the same IRI minted by Accounts for that customer

### Schemas

- **Avro** (Kafka): `schemas/avro/risk-events-v1.0.avsc`
- **Iceberg** (Lake): `schemas/iceberg/fraud_scores.schema`, `kyc_verdicts.schema`
- **RDF** (Semantic): `ontology-extensions.ttl` (RiskProfile and cross-domain properties)

### Ingest Job

- **File**: `ingest/ingest_job.py`
- **Trigger**: Continuous Spark Structured Streaming
- **SLA**: 10-minute freshness, 99.99% availability

## File Structure

```
domains/risk-compliance/
├── README.md                            # This file
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
│   │   └── risk-events-v1.0.avsc       # Avro schema for Kafka
│   └── iceberg/
│       └── schemas.py                   # Iceberg table schema definitions
│
├── src/main/python/semantic/
│   ├── iri_resolver.py                 # Mint RiskProfile IRIs
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
│   └── risk-scores.yaml                # Data product specification
│
└── queries/
    ├── high-risk-customers.sql         # Query: HIGH/CRITICAL risk profiles
    ├── compliance-violations.sql        # Query: NON_COMPLIANT/SUSPENDED status
    └── kyc-status-report.sql           # Query: KYC verification status summary
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
# Adjust values if needed (default ports are 5432 for PostgreSQL, 3032 for Jena)
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
- **Jena Fuseki** (port 3032): Hosts RDF triple store with SPARQL endpoint

### 4. Verify Services

Check PostgreSQL:
```bash
docker-compose exec postgres psql -U risk_compliance_user -d risk_compliance_db -c "SELECT 1;"
```

Check Jena Fuseki:
```bash
curl -s http://localhost:3032/ | head -20
```

Check SPARQL endpoint is accessible:
```bash
curl -s "http://localhost:3032/risk-compliance/sparql?query=SELECT%20*%20%7B%7D%20LIMIT%201" | jq .
```

### 5. Load Sample Data (Optional)

```bash
# Create sample risk profile records
docker-compose exec postgres psql -U risk_compliance_user -d risk_compliance_db < data/sample-risk-profiles.sql
```

### 6. Run Unit Tests

```bash
pytest src/main/python/semantic/tests/ -v
```

Expected output:
```
test_iri_resolver.py::TestIriResolver::test_mint_risk_profile_iri_deterministic PASSED
test_iri_resolver.py::TestIriResolver::test_mint_risk_profile_iri_case_insensitive PASSED
test_cross_domain_resolver.py::TestCrossDomainResolver::test_resolve_customer_iri_deterministic PASSED
...
===== 15 passed in 0.52s =====
```

### 7. Run Integration Tests

```bash
pytest tests/test_integration_e2e.py -v
```

Expected output shows:
- RDF transformation from Silver tables
- SPARQL query execution
- Cross-domain customer linking verification
- Enum validation for risk levels, KYC status, and compliance status
- All tests passing (20+ test cases)

## IRI Minting Rules

The Risk/Compliance domain mints IRIs deterministically using the `iri-minting-rules.yaml` specification.

### RiskProfile IRIs

**Key Field**: `risk_id`  
**Algorithm**: Direct identity-based (no hashing)  
**Format**: `https://chakracommerce.com/risk-profile#{id}`

**Why**: Risk profile IDs are globally unique in the source system. No normalization is needed.

**Example**:
- Input: `risk_001`
- Output: `https://chakracommerce.com/risk-profile#risk_001`

**Determinism**: Same risk ID always produces the same IRI (idempotent).

### Cross-Domain Customer Resolution

**Key Fields**: `customer_email`, `customer_kyc_id`  
**Algorithm**: SHA-256 hashing (same as Accounts domain)  
**Format**: `https://chakracommerce.com/customer#{hash}`

**Why**: Customers are owned by the Accounts domain. Risk profiles must reference the same Customer IRIs minted by Accounts to enable deduplication.

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

The Risk/Compliance domain defines RDF entities and properties in `ontology-extensions.ttl`.

### Entity Types

**fintech:RiskProfile**  
Represents a risk assessment and compliance status for a customer. Key properties:

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `fintech:riskProfileId` | xsd:string | Risk assessment identifier | `risk_001` |
| `fintech:riskScore` | xsd:decimal | Numeric risk score (0.0 to 1.0) | `0.92` |
| `fintech:riskLevel` | xsd:string | Risk classification (LOW, MEDIUM, HIGH, CRITICAL) | `HIGH` |
| `fintech:complianceStatus` | xsd:string | Compliance status (COMPLIANT, UNDER_REVIEW, NON_COMPLIANT, SUSPENDED) | `UNDER_REVIEW` |
| `fintech:kycStatus` | xsd:string | KYC verification status (NOT_STARTED, IN_PROGRESS, VERIFIED, REJECTED, EXPIRED) | `VERIFIED` |
| `fintech:fraudFlagsCount` | xsd:integer | Number of fraud flags or incidents | `2` |
| `fintech:lastReviewDate` | xsd:dateTime | Timestamp of most recent review | `2026-05-30T14:23:15Z` |
| `fintech:nextReviewDate` | xsd:dateTime | Scheduled timestamp for next review | `2026-06-30T14:23:15Z` |
| `fintech:reviewNotes` | xsd:string | Human-written assessment notes (optional) | `High transaction volume flagged` |
| `fintech:forCustomer` | fintech:Customer | Reference to customer IRI (Accounts domain) | `https://chakracommerce.com/customer#a1b2c3d4` |

### Metadata Properties

All RDF entities include source system metadata:
- `sourceSystem` - Origin system (e.g., `risk_compliance`)
- `sourceIngestionTime` - When data was loaded

### Full RDF Schema

For complete ontology details including class definitions, property domains/ranges, and shared properties, see:
- `ontology-extensions.ttl` (Risk/Compliance domain-specific definitions)
- `../../docs/case-study/fintech-semantic-integration/shared-ontology.ttl` (Shared fintech ontology)

## Risk Scoring Methodology

The Risk/Compliance domain uses a risk score ranging from 0.0 (no risk) to 1.0 (maximum risk), with categorical classifications:

### Risk Levels

- **LOW** (0.0 - 0.25): Minimal fraud/compliance risk. Normal customer activity.
- **MEDIUM** (0.25 - 0.50): Moderate risk indicators. Routine review recommended.
- **HIGH** (0.50 - 0.75): Elevated risk signals. Enhanced due diligence required.
- **CRITICAL** (0.75 - 1.0): Severe risk flags. Immediate intervention and escalation required.

### Compliance Status Meanings

- **COMPLIANT**: Customer passes all compliance checks. Full regulatory approval.
- **UNDER_REVIEW**: Customer under investigation. Pending compliance verification.
- **NON_COMPLIANT**: Customer fails compliance requirements. Violations detected.
- **SUSPENDED**: Customer account suspended pending compliance resolution. Access restricted.

### KYC Status Flow

The Know Your Customer (KYC) verification follows a state machine:

```
NOT_STARTED → IN_PROGRESS → VERIFIED (✓ approved)
              ↓
           REJECTED (✗ failed verification)

VERIFIED → EXPIRED (after TTL threshold)
```

## Cross-Domain Integration

The Risk/Compliance domain integrates with the Accounts domain through deterministic customer IRI resolution. This enables entity deduplication and federated SPARQL queries.

### How Cross-Domain Resolution Works

1. **Risk domain** receives risk profile records with `customer_email` and `customer_kyc_id`
2. **CrossDomainResolver** applies the same normalization and hashing algorithm as Accounts domain
3. Result is a Customer IRI that matches what Accounts domain minted
4. Risk profile is linked via `fintech:forCustomer` property
5. Queries can now traverse from risk profile → customer (from Accounts domain)

### Code Example: Using CrossDomainResolver

```python
from semantic.cross_domain_resolver import CrossDomainResolver

# Create resolver
resolver = CrossDomainResolver()

# Resolve customer IRI from risk profile data
customer_iri = resolver.resolve_customer_iri(
    customer_email="john@acme.com",
    customer_kyc_id="kyc_123"
)

print(customer_iri)
# Output: https://chakracommerce.com/customer#a1b2c3d4
```

### Cross-Domain SPARQL Federation

Query risk profiles with customer data from Accounts domain using SPARQL SERVICE clause:

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
PREFIX cust: <https://chakracommerce.com/ontology/customer/>

SELECT ?riskProfile ?customer ?email ?riskScore ?riskLevel
WHERE {
  # Query risk profiles in Risk domain
  ?riskProfile a fintech:RiskProfile ;
               fintech:riskScore ?riskScore ;
               fintech:riskLevel ?riskLevel ;
               fintech:forCustomer ?customerIri .
  
  # Federated query to Accounts domain for customer details
  SERVICE <http://localhost:3031/accounts/sparql> {
    ?customerIri cust:email ?email ;
                 cust:name ?customer .
  }
}
LIMIT 20
```

## Running Tests

### Unit Tests

Unit tests verify the core semantic transformation components:

```bash
pytest src/main/python/semantic/tests/ -v
```

**Test Coverage**:

- **test_iri_resolver.py** (8 tests)
  - IRI determinism (same ID → same IRI)
  - Case insensitivity (RISK_001 = risk_001)
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
  - Enum validation for risk levels, KYC status, compliance status

### Integration Tests

End-to-end tests verify the complete pipeline:

```bash
pytest tests/test_integration_e2e.py -v
```

**Test Coverage** (20+ test cases):
- Load sample risk profile data (5+ profiles)
- Transform to RDF triples
- Verify cross-domain customer IRI linking
- Execute SPARQL queries on generated RDF
- Validate metadata tagging and ingestion timestamps
- Check all RDF triples are well-formed
- Enum validation: risk levels (LOW, MEDIUM, HIGH, CRITICAL)
- Enum validation: KYC status (NOT_STARTED, IN_PROGRESS, VERIFIED, REJECTED, EXPIRED)
- Enum validation: compliance status (COMPLIANT, UNDER_REVIEW, NON_COMPLIANT, SUSPENDED)
- Test multiple risk profiles for same customer (deduplication)

### Run All Tests

```bash
pytest src/main/python/semantic/tests/ tests/ -v
```

Expected output: **30+ tests passing** with details on RDF transformation, IRI minting, and cross-domain resolution.

### Test with Coverage

```bash
pytest src/main/python/semantic/tests/ tests/ --cov=src/main/python/semantic --cov-report=html
```

View coverage report in `htmlcov/index.html`.

## SPARQL Endpoint

The Risk/Compliance domain exposes a SPARQL endpoint via Jena Fuseki for querying RDF triples.

### Connection Details

- **URL**: `http://localhost:3032/risk-compliance/sparql` (default)
- **Available Endpoints**:
  - `/query` - SPARQL SELECT queries
  - `/update` - SPARQL INSERT/DELETE updates
  - `/gsp-r` - Graph Store Protocol read
  - `/gsp-rw` - Graph Store Protocol read/write

### Health Check

```bash
curl -s "http://localhost:3032/risk-compliance/sparql?query=SELECT%20*%20%7B%7D%20LIMIT%201"
```

### Example: Count All Risk Profiles

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT (COUNT(?riskProfile) AS ?count)
WHERE {
  ?riskProfile a fintech:RiskProfile .
}
```

Query via curl:
```bash
curl -s "http://localhost:3032/risk-compliance/sparql" \
  --data-urlencode 'query=PREFIX fintech: <https://chakracommerce.com/ontology/fintech/> SELECT (COUNT(?riskProfile) AS ?count) WHERE { ?riskProfile a fintech:RiskProfile . }'
```

### Example: Find All HIGH Risk Profiles

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT ?riskProfile ?riskScore ?complianceStatus
WHERE {
  ?riskProfile a fintech:RiskProfile ;
               fintech:riskLevel "HIGH" ;
               fintech:riskScore ?riskScore ;
               fintech:complianceStatus ?complianceStatus .
}
ORDER BY DESC(?riskScore)
LIMIT 20
```

### Example: Find CRITICAL Risk Profiles

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT ?riskProfile ?riskScore ?fraudFlags ?lastReview
WHERE {
  ?riskProfile a fintech:RiskProfile ;
               fintech:riskLevel "CRITICAL" ;
               fintech:riskScore ?riskScore ;
               fintech:fraudFlagsCount ?fraudFlags ;
               fintech:lastReviewDate ?lastReview .
}
ORDER BY DESC(?riskScore)
```

### Example: List All NON_COMPLIANT Customers

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT ?riskProfile ?complianceStatus ?kycStatus
WHERE {
  ?riskProfile a fintech:RiskProfile ;
               fintech:complianceStatus "NON_COMPLIANT" ;
               fintech:kycStatus ?kycStatus .
}
```

### Example: Find Suspended Accounts

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>

SELECT ?riskProfile ?riskLevel ?reviewNotes
WHERE {
  ?riskProfile a fintech:RiskProfile ;
               fintech:complianceStatus "SUSPENDED" ;
               fintech:riskLevel ?riskLevel ;
               fintech:reviewNotes ?reviewNotes .
}
```

### Example: SPARQL JOIN with Accounts Domain (Federation)

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
PREFIX cust: <https://chakracommerce.com/ontology/customer/>

SELECT ?riskProfile ?riskScore ?riskLevel ?email
WHERE {
  # Risk profiles with HIGH or CRITICAL risk
  ?riskProfile fintech:riskLevel ?riskLevel ;
               fintech:riskScore ?riskScore ;
               fintech:forCustomer ?customerIri .
  FILTER (?riskLevel IN ("HIGH", "CRITICAL"))
  
  # Federated lookup to Accounts domain
  SERVICE <http://localhost:3031/accounts/sparql> {
    ?customerIri cust:email ?email .
  }
}
ORDER BY DESC(?riskScore)
```

### Using Python with RDFLib

```python
from rdflib import Graph, Namespace, RDF

g = Graph()
g.parse("http://localhost:3032/risk-compliance/sparql", format="sparql")

FINTECH = Namespace('https://chakracommerce.com/ontology/fintech/')

# Query all CRITICAL risk profiles
for risk_profile in g.subjects(predicate=FINTECH.riskLevel, object="CRITICAL"):
    score = g.value(risk_profile, FINTECH.riskScore)
    print(f"Risk Profile: {risk_profile}, Score: {score}")
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

Example: Adding a new property `fintech:amlCheckStatus`:

```turtle
# In ontology-extensions.ttl
fintech:amlCheckStatus
  a rdf:Property ;
  rdfs:domain fintech:RiskProfile ;
  rdfs:range xsd:string ;
  rdfs:label "AML Check Status" ;
  rdfs:comment "Anti-Money Laundering check completion status" ;
  fintech:owningDomain "risk_compliance" .
```

Then update `silver_to_rdf.py`:
```python
if 'aml_check_status' in row and pd.notna(row['aml_check_status']):
    self.g.add((rp_iri, self.FINTECH.amlCheckStatus,
               Literal(str(row['aml_check_status']))))
```

### Adding Test Cases

Unit tests in `src/main/python/semantic/tests/`:
```python
def test_new_risk_metric(self):
    """Test: New risk metric works correctly."""
    result = calculate_new_metric()
    assert result == expected_value
```

Integration tests in `tests/test_integration_e2e.py`:
```python
def test_new_compliance_scenario(self, transformer, sample_data):
    """Test: New compliance scenario in end-to-end pipeline."""
    graph = transformer.transform_risk_profiles_to_rdf(sample_data)
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

g = transformer.transform_risk_profiles_to_rdf(df)
for s, p, o in g:
    print(f"{s} {p} {o}")
```

**Check SPARQL endpoint directly**:
```bash
curl -s "http://localhost:3032/risk-compliance/sparql?query=SELECT%20*%20WHERE%20%7B%20%3Fs%20%3Fp%20%3Fo%20%7D%20LIMIT%205"
```

## Integration with Other Domains

### Accounts Domain (Customer Owner)

The **Accounts domain** owns the Customer entity and mints Customer IRIs. The Risk/Compliance domain:
- Does NOT mint Customer IRIs
- Uses `CrossDomainResolver` to deterministically derive the same Customer IRI
- Links risk profiles to customers via `fintech:forCustomer` property
- Allows queries to traverse from risk profile → customer data

**Related**: See `../accounts/README.md` for Customer IRI minting rules.

### Transactions Domain (Transaction Events)

The **Transactions domain** provides real-time transaction event data. Risk/Compliance domain may:
- Query transaction volume per customer
- Link fraud flags to specific transactions
- Use transaction patterns in risk scoring

**Related**: See `../transactions/README.md` for transaction data and SPARQL federation examples.

### Three-Domain Federation

Query across all three domains (Accounts, Transactions, Risk):

```sparql
PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
PREFIX cust: <https://chakracommerce.com/ontology/customer/>
PREFIX risk: <https://chakracommerce.com/ontology/risk/>

SELECT ?customer ?name ?email ?transactionCount ?riskLevel ?riskScore
WHERE {
  # Customer from Accounts domain
  SERVICE <http://localhost:3031/accounts/sparql> {
    ?customerIri cust:name ?name ; cust:email ?email .
  }
  
  # Risk profile from Risk domain
  ?riskProfile fintech:forCustomer ?customerIri ;
               fintech:riskLevel ?riskLevel ;
               fintech:riskScore ?riskScore .
  
  # Count transactions from Transactions domain
  SERVICE <http://localhost:3031/transactions/sparql> {
    SELECT ?customerIri (COUNT(?transaction) AS ?transactionCount) WHERE {
      ?transaction fintech:transactionDebtor ?customerIri .
    }
    GROUP BY ?customerIri
  }
}
```

## Related Documentation

- **[Accounts Domain README](../accounts/README.md)** — Customer entity owner, IRI minting for customers
- **[Transactions Domain README](../transactions/README.md)** — Transaction event data, SPARQL federation patterns
- **[Fintech Semantic Integration Case Study](../../docs/case-study/fintech-semantic-integration/case-study-guide.md)** — Overall semantic layer architecture, cross-domain patterns, federation examples
- **Shared Ontology** — `../../docs/case-study/fintech-semantic-integration/shared-ontology.ttl` (fintech ontology with all entity and property definitions)

## Query Examples

Reference queries for common scenarios:

- **High Risk Customers**: `queries/high-risk-customers.sql`
- **Compliance Violations**: `queries/compliance-violations.sql`
- **KYC Status Report**: `queries/kyc-status-report.sql`

## Testing

- **Unit**: IRI determinism, cross-domain resolution, RDF transformation, enum validation
- **Integration**: Silver → RDF pipeline, SPARQL queries, entity linking, metadata annotation
- **Compliance**: Risk level classifications, KYC/AML status tracking, review scheduling

## Operational Runbooks

See `../../docs/domains/risk-compliance/` for:
- Risk scoring methodology and tuning
- KYC/AML workflow and escalation procedures
- Compliance status transition rules
- SPARQL query optimization for compliance reporting
