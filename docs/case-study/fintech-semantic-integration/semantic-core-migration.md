# Semantic core migration and identity runbook

This page is for anyone who produces or consumes the fintech semantic layer after the
[semantic drift fix](semantic-drift.md). It covers:

1. the term renames consumers must make;
2. the customer IRI change and how to reload;
3. how to set up, distribute and rotate the identity key;
4. how validation gates producers;
5. how to run the tests.

## 1. Term renames

The core is `semantics/core/fintech-core.ttl`, version `1.0.0`
(`https://chakracommerce.com/ontology/fintech/core/1.0.0`). Domain extensions import it
by version IRI and may not redefine its terms. Each deprecated name still resolves in the
core, marked `owl:deprecated true` with `owl:equivalentProperty` pointing at its
replacement, so old queries can be found and migrated.

| Deprecated name | Use instead | Owner |
|---|---|---|
| `fintech:riskCustomer` | `fintech:forCustomer` | core |
| `fintech:accountCustomer` | `fintech:accountOwner` | core |
| `fintech:email` | `fintech:customerEmail` | Accounts extension |
| `fintech:name` | `fintech:customerName` | Accounts extension |
| `fintech:currentBalance` | `fintech:accountBalance` (`xsd:decimal`) | Accounts extension |
| `fintech:decimal` (datatype) | `xsd:decimal` | XSD |
| `?ticketCount` in the churn query | removed (no domain binds it) | federation |

Any producer output that still uses a deprecated name fails the
`NoDeprecatedTermsShape` shape.

## 2. The customer IRI change

Customer IRIs are now 64 hex characters, not 8. **Every customer IRI changes.** The old
IRIs cannot be converted to the new ones, because the new ones depend on the key and
the old ones were truncated.

To reload:

1. Set `FINTECH_IRI_KEY` for every producer (see section 3).
2. Re-run each domain's producer from the same silver tables. Customers mint their new
   IRIs from `(email, kyc_id)`.
3. Drop the old graphs, then load the new output. Any 8-hex customer IRI fails the
   core customer-IRI shape, so a graph that mixes old and new IRIs cannot be written.
4. Any saved IRI held by a consumer must be re-resolved from `(email, kyc_id)`. Use the
   same library so the consumer gets the same IRI as the producer.

Consumers that resolve customers themselves must call `shared/semantic/identity.py` (or
the domain's `CrossDomainResolver`, which delegates to it). Do not reimplement the rule.

## 3. Identity key runbook

The customer IRI rule is:

```
IRI = https://chakracommerce.com/customer# + HMAC-SHA256(key, normalize(email) + "|" + normalize(kyc_id))
normalize(x) = str(x).lower().strip()        (64 lowercase hex characters)
```

The key is read from `FINTECH_IRI_KEY`. There is no default. If the variable is unset or
empty, minting raises `IriKeyMissingError`.

### Create the key

Generate a random key of at least 32 bytes, for example:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Store and distribute it

- Store the key in your secret manager, not in the repo.
- Give the same value to every producer and every consumer that mints customer IRIs.
  If two producers have different keys, their customer IRIs will not match, and joins
  will silently return zero rows.
- Do not use the test key in `conftest.py` (`test-only-iri-key-do-not-use-in-production`)
  or the demo key anywhere except tests and demos.

### Rotate the key

Rotating the key re-mints every customer IRI, so rotation is a full reload (section 2).

1. Generate the new key and store it alongside the old one.
2. Switch every producer to the new key and reload all three domains in one window.
3. Switch every consumer that mints IRIs.
4. Retire the old key once nothing reads the old graphs.

Golden vectors (`semantics/core/identity-vectors.json`) pin the rule under the test key.
They do not change on rotation, because they use a fixed test key.

## 4. Validation gates

Producers must conform to the shapes before they write.

| Domain | Gate |
|---|---|
| Accounts | `RdfWriter.write_to_jena` and `write_to_file` call `assert_conforms` first |
| Transactions | `RdfWriter.write_to_jena` and `write_to_file` call `assert_conforms` first |
| Risk / Compliance | No writer yet. The contract test `tests/contract/test_shapes_on_fixtures.py` validates its output. Add the same gate when a writer exists. |

A violation raises `SemanticValidationError` with the full report. The job fails. It
does not write a partial graph.

To check a graph by hand:

```python
from shared.semantic.validation import validate_graph
conforms, report_graph, report_text = validate_graph(graph, "accounts")
print(report_text)
```

## 5. Run the tests

Each domain has its own `semantic` package, and they cannot share one pytest session
(the package names collide), so run them one at a time:

```bash
make test-semantic
```

That runs the three domain semantic suites, the three integration suites, and the
contract tests in `tests/contract/`:

- `test_identity_vectors.py`: golden vectors through the library and every domain's
  resolver.
- `test_federated_churn.py`: the churn query returns the known high-risk customer, and
  every selected variable is bound.
- `test_shapes_on_fixtures.py`: each domain's real producer output conforms.
- `test_shapes_reject_drift.py`: each named drift fails validation.

## Dependencies

- `pyshacl` is required by the validation gates. It is pinned in `requirements.txt`.
- The domain requirements pin `rdflib==6.3.2`. The tests and demos were run on rdflib 7.x.
  Re-run `make test-semantic` after changing either pin.
- Domain code imports `shared.semantic`, so the repo root must be on `PYTHONPATH` at
  runtime, as it already is for tests.
