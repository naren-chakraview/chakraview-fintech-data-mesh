# After: the fixed design

This page describes the semantic layer as it is now, after the
[semantic drift fix](semantic-drift.md). For the drifted design it replaces, see
[Before: the drifted design](semantic-drift-before.md).

## The layout

| Path | What it is |
|---|---|
| `semantics/core/fintech-core.ttl` | The one shared ontology, version 1.0.0 (`https://chakracommerce.com/ontology/fintech/core/1.0.0`). Entity classes, link properties, provenance, and deprecated aliases. |
| `semantics/core/identity-vectors.json` | Golden vectors for the customer IRI rule, computed by an independent reference. |
| `semantics/shapes/` | SHACL shapes: `core-shapes.ttl` for every domain, plus one file per domain. |
| `shared/semantic/identity.py` | The customer IRI rule. Owned by Accounts. Every resolver delegates to it. |
| `shared/semantic/validation.py` | Validates a producer graph against the shapes and raises on violation. |
| `domains/*/ontology-extensions.ttl` | Each domain's attributes. Each imports the core by version IRI. |
| `domains/federation/queries/churn-analysis-federated.sparql` | The one federated churn query. |

## The rules

**One name per link.** The core fixes `accountOwner`, `transactionDebtor`,
`transactionCreditor` and `forCustomer`. Attribute names live in the owning domain's
extension: `customerName`, `customerEmail`, `accountBalance`, and so on. Each deprecated
name is still in the core, marked `owl:deprecated`, pointing at its replacement.

**One identity rule.** A customer IRI is:

```
https://chakracommerce.com/customer#<HMAC-SHA256(FINTECH_IRI_KEY, normalize(email) + "|" + normalize(kyc_id))>
```

The digest is the full 64 lowercase hex characters. `normalize(x)` is `str(x).lower().strip()`.
The key comes from `FINTECH_IRI_KEY` and has no default. Rotating it re-mints every
customer. The procedure is in the [migration and identity runbook](semantic-core-migration.md).

**Typed values.** Balances, amounts and risk scores are `xsd:decimal`, built from
`Decimal(str(value))`. Dates and ingestion times are `xsd:dateTime`.

**Validation before write.** The Accounts and Transactions `RdfWriter` methods check the
graph against the core and domain shapes first. A violation raises
`SemanticValidationError` with the full report, so the job fails and writes nothing.
The Risk/Compliance domain has no writer yet. Its output is validated in the contract
tests.

## What the tests check

`make test-semantic` runs the domain suites, the integration suites and the contract
tests in `tests/contract/`:

| Test | Checks |
|---|---|
| `test_identity_vectors.py` | Every golden vector through the library and every domain's resolver. The D4 collision pair mints different IRIs. A missing key refuses to mint. |
| `test_federated_churn.py` | The churn query returns the known high-risk customer. Every selected variable is bound. |
| `test_shapes_on_fixtures.py` | Each domain's producer output conforms to its shapes. |
| `test_shapes_reject_drift.py` | Each named drift, on its own, fails validation. |

## The results

The demos run the same data through the after code:

| Demo | Result |
|---|---|
| Consumer query written from the core (`forCustomer`) | `1 row(s)`: `john@acme.com`, risk score `0.92` |
| The D4 pair | two different 64-hex IRIs |
| Collision odds, 77,000 customers, 256 bits | about 3 × 10⁻⁶⁸ |
| `SUM` over transaction amounts | `4500.0` |
| Shapes validation of after output | `Conforms: True` |

## Run it

```bash
pip install -r requirements.txt          # includes pyshacl
export FINTECH_IRI_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
make test-semantic
make semantic-drift-demo
```

Set `FINTECH_IRI_KEY` yourself for real runs. The demos and tests set a public key when
it is unset, and that key must not be used in production.
