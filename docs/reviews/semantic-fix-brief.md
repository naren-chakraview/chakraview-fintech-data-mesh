# Fix brief: fintech-data-mesh semantic integration (before and after)

**Repo:** `naren-chakraview/chakraview-fintech-data-mesh` at `44f2cba`
**Why:** article 2 of the data mesh series ("Data products need meaning, not just schemas") uses this repo as its evidence. It shows the drift found in the semantic layer and the fix.
**Shape of the change:** the repo is a learning tool, so keep **both** versions. The drifted design stays in the repo as a frozen, documented, runnable "before". The domain code becomes the fixed "after". A docs page puts the two side by side.

## What is wrong today (the "before")

| # | Drift | Where |
|---|---|---|
| D1 | **Competing link properties.** The shared ontology links risk to customer with `fintech:riskCustomer`; Risk's extension, producer and the federated query use `fintech:forCustomer`. Same split for `email`/`customerEmail`, `name`/`customerName`, `accountCustomer`/`accountOwner`. A query written from the published core returns zero rows, with no error. | `docs/case-study/fintech-semantic-integration/shared-ontology.ttl`, `domains/*/ontology-extensions.ttl`, `domains/*/src/main/python/semantic/silver_to_rdf.py` |
| D2 | **Four "shared" ontologies.** The docs copy (365 lines) and three per-domain test copies (78, 72, 70 lines) all differ. | `domains/*/src/main/python/semantic/tests/shared-ontology-test.ttl` |
| D3 | **Identity rule copied three times.** `IriResolver` (Accounts) and two `CrossDomainResolver` copies each reimplement SHA-256(email \| kyc_id). Each copy's tests check only itself, so drift between copies passes CI. | `domains/*/src/main/python/semantic/{iri_resolver,cross_domain_resolver}.py` and their tests |
| D4 | **32-bit identifiers.** The hash is truncated to 8 hex characters. Collision odds are 50% at about 77,000 customers and 69% at 100,000. Concrete example: `customer111830@example.com` / `KYC0111830` and `customer130865@example.com` / `KYC0130865` both mint `customer#15e5a0c2`. (data-engineering-patterns uses 16 characters for the same job.) | same files |
| D5 | **Email-derived identity.** An unkeyed hash of a low-entropy identifier can be reversed by guessing. | same files |
| D6 | **Numbers that are not numbers.** Balances and amounts are typed `fintech:decimal`, which is defined nowhere, and built from Python `float`. SPARQL `SUM` over them raises a type error; strict engines drop numeric filters. | `accounts/.../silver_to_rdf.py:88`, `transactions/.../silver_to_rdf.py:58` |
| D7 | **No validation.** No SHACL shapes; nothing checks a producer's output against the core. | (absent) |
| D8 | **Two churn queries.** `domains/federation/queries/` and the docs copy differ; the docs version selects `?ticketCount` without binding it. | `churn-analysis-federated.sparql` (both) |

## Part 1: preserve the "before"

1. **Tag the current state:** `git tag semantic-drift-before 44f2cba` (push the tag). Anyone can check out the whole drifted repo.
2. **Freeze a self-contained copy** under `examples/semantic-drift/before/`:
   - the four ontology copies as they are now;
   - the three resolver copies and their tests;
   - the two `silver_to_rdf.py` snippets that type values as `fintech:decimal`;
   - both churn queries;
   - a `README.md` with one short paragraph per drift (D1 to D8), each pointing at the file that shows it.
   These files are reference material. Nothing in the main code imports them.

## Part 2: build the "after" in the main code

### A1. One shared core, versioned, never copied
- Create `semantics/core/fintech-core.ttl` with `owl:versionIRI` (for example `.../ontology/fintech/core/1.0.0`). It holds only:
  - the entity classes: `Customer`, `Account`, `Transaction`, `Counterparty`, `RiskProfile`;
  - the cross-domain link properties: `accountOwner`, `transactionDebtor`, `transactionCreditor`, `forCustomer`;
  - provenance: `sourceSystem`, `sourceIngestionTime`;
  - the identity rules, as documented annotations.
- **Resolve each competing pair once.** Keep the names producers already use (`forCustomer`, `accountOwner`). Mark the losers `owl:deprecated true` with `owl:equivalentProperty`, so old queries can be migrated, and so a SHACL rule (A5) can reject them.
- Move attribute properties to their owning domain's extension, for example `customerName` and `customerEmail` to Accounts. Remove the duplicates (`name`, `email`, `currentBalance` and so on) from the core.
- Domain extensions `owl:imports` the core by its version IRI and may not redefine core terms.
- Delete the per-domain `shared-ontology-test.ttl` copies. Tests load `semantics/core/fintech-core.ttl`.
- The docs page embeds or links the core file; it no longer carries its own copy.

### A2. Identity as one library, owned by Accounts
- Create `shared/semantic/identity.py` (owner: Accounts domain, stated in the module docstring and `CODEOWNERS` if used) with `mint_customer_iri(email, kyc_id)`.
- Use **HMAC-SHA256 with the full 64-hex digest**, keyed by `FINTECH_IRI_KEY` from the environment. Keying closes D5. Document that every producer must receive the same key, distributed like any other secret, and that rotating it re-mints every customer IRI.
- Publish **golden vectors** in `semantics/core/identity-vectors.json`: about ten (email, kyc_id, expected IRI) cases under a fixed test key. Include case and whitespace variants and the D4 collision pair, which must now mint different IRIs.
- Replace both `CrossDomainResolver` copies with imports of the library.
- Add `tests/contract/test_identity_vectors.py`. It runs the golden vectors through every domain's code path that mints or resolves customer IRIs, so a domain that drifts fails CI.

### A3. Datatypes a machine can compute with
- Type balances and amounts as `xsd:decimal`, built from `Decimal(str(value))`, not `float`.
- Type dates as `xsd:dateTime`, and add explicit datatypes wherever a producer emits a number or a date.

### A4. Producers validate before they publish (shift-left, executable)
- Add SHACL shapes in `semantics/shapes/`: `core-shapes.ttl` for every domain, plus one file per domain. They must cover:
  - customer IRIs match `^https://chakracommerce.com/customer#[0-9a-f]{64}$`;
  - `forCustomer`, `accountOwner` and `transactionDebtor` are required where the core says so, and point at a `fintech:Customer`;
  - amounts and balances are `xsd:decimal`;
  - deprecated core terms (`riskCustomer`, `accountCustomer`, `email`, `name`) are **not** used;
  - `sourceSystem` and `sourceIngestionTime` are present.
- In each domain's producer, run `pyshacl` on the graph after `silver_to_rdf` and before writing. A violation fails the job with a readable report.
- CI runs the shapes against each domain's fixture output.

### A5. One churn query, tested
- Keep a single `domains/federation/queries/churn-analysis-federated.sparql`. Fix the unbound variable, and have the docs include this file instead of carrying a copy.
- Add `tests/contract/test_federated_churn.py`. It loads each domain's fixture output into local graphs, runs the query (with `SERVICE` rewritten to named graphs, or the three graphs unioned), and asserts the known high-risk customer comes back.

### A6. Out of scope here (article 3)
The Fuseki configs expose open SPARQL update and graph-store read/write endpoints, and the Accounts graph serves customer names and emails unmasked. Do not fix it in this change. Add it to the docs as a known gap ("a second read path governance must cover") so article 2 can link to it.

## Part 3: show the difference

### L1. Runnable before-and-after demos in `examples/semantic-drift/`
One script per drift. Each runs the "before" and the "after" and prints both results:
- `demo_empty_join.py` (D1): build the three domain graphs as the before code produces them, run the query a consumer would write from the published core (`riskCustomer`), and print 0 rows. Then run the after core's query on after output, and print the expected rows.
- `demo_identity_collision.py` (D3, D4): mint the D4 pair with the before rule, showing the same IRI, and with the after library, showing different IRIs. Print the birthday-bound odds at 10k, 77k, 100k and 1M customers for 32-bit and 256-bit digests.
- `demo_decimal_sum.py` (D6): `SUM` over before amounts raises the type error; over after amounts it returns the total.
- `demo_shacl_catches_drift.py` (D1, D6, D7): validate before output against the after shapes and print the violation report, one line per drift. Then validate after output and print `Conforms: True`.
- A `Makefile` target `make semantic-drift-demo` runs all four.

### L2. Docs page: "Semantic drift: before and after"
- Add `docs/case-study/fintech-semantic-integration/semantic-drift.md` to the mkdocs nav, under the case study. It contains:
  - a side-by-side table, one row per drift: before (file and behavior), after (file and behavior), and how it is now caught (contract test, SHACL shape or type);
  - the empty-join example, with both queries and both results;
  - the collision example and the odds;
  - how to run the demos, and how to check out the `semantic-drift-before` tag;
  - two diagrams: the domain-owned semantics architecture, and where drift is caught (consumer versus producer). The article's SVGs can be reused once they exist.
- Update the shift-left blog post and the federation guide so they refer to the single core file and the identity library. Add a short "what changed" note at the top of each, linking to the drift page.

## Acceptance

- `git checkout semantic-drift-before` reproduces the old repo; `examples/semantic-drift/before/` holds the frozen copies.
- There is exactly one shared core file; no test or doc carries a copy.
- Golden vectors pass in every domain; changing one domain's minting code fails CI.
- The D4 pair mints different IRIs under the after library.
- Every domain's fixture output conforms to the SHACL shapes. Before output does not, and the report names each drift.
- `SUM` over after amounts works.
- The federated churn contract test passes and returns the known customer.
- `make semantic-drift-demo` prints the before and after results for all four demos.
- The drift page is in the published site navigation.
