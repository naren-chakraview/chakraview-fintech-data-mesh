# Semantic drift: the frozen "before"

This directory holds the drifted semantic layer as it was at commit `44f2cba`, tagged
`semantic-drift-before`. Nothing in the main code imports it. It exists so you can run
the drift and compare it with the fix. The paths match the repo, so each file below is
at the same path it had at the tag.

To check out the whole drifted repo instead: `git checkout semantic-drift-before`.

## D1: competing link names

The published ontology (`docs/case-study/fintech-semantic-integration/shared-ontology.ttl`)
said `fintech:riskCustomer`, `fintech:accountCustomer`, `fintech:email` and `fintech:name`.
The producers wrote `forCustomer`, `accountOwner` and `customerEmail`/`customerName`. A
consumer query written from the published core returned zero rows without an error. See
`demo_empty_join.py`.

## D2: four "shared" ontologies

The docs copy (365 lines) and three test copies under
`domains/*/src/main/python/semantic/tests/shared-ontology-test.ttl` (78, 72 and 70 lines)
all differed.

## D3: identity rule copied three times

`domains/accounts/src/main/python/semantic/iri_resolver.py` and the two
`cross_domain_resolver.py` files under `domains/risk-compliance` and
`domains/transactions` each reimplemented SHA-256 over `email|kyc_id`. Each copy's tests
checked only itself, so drift between the copies passed CI.

## D4: 32-bit identifiers

The hash was truncated to 8 hex characters. `customer111830@example.com` / `KYC0111830`
and `customer130865@example.com` / `KYC0130865` both mint `customer#15e5a0c2`. See
`demo_identity_collision.py`.

## D5: email-derived identity

The hash was unkeyed, and the input is a low-entropy identifier, so it could be reversed
by guessing.

## D6: numbers that are not numbers

`domains/accounts/src/main/python/semantic/silver_to_rdf.py` and
`domains/transactions/src/main/python/semantic/silver_to_rdf.py` typed balances and
amounts as `fintech:decimal`, which is defined nowhere, and built them from Python
`float`. `SUM` over them raises a type error. See `demo_decimal_sum.py`.

## D7: no validation

No SHACL shapes existed, and nothing checked a producer's output against the core. See
`demo_shacl_catches_drift.py`.

## D8: two churn queries

`domains/federation/queries/churn-analysis-federated.sparql` and
`docs/case-study/fintech-semantic-integration/churn-analysis-federated.sparql` differed.
The federation copy selected `?ticketCount`, which nothing binds.
