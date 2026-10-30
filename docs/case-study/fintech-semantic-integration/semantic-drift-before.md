# Before: the drifted design

This page describes the semantic layer as it was at commit `44f2cba`, before the
[semantic drift fix](semantic-drift.md). It is kept as a frozen, runnable reference.
Nothing in the main code imports it.

## Get the drifted repo

```bash
git checkout semantic-drift-before     # the whole repo at 44f2cba
```

The frozen copies of the drifted files are in `examples/semantic-drift/before/`, at the
same paths they had in the repo.

## How the layer was built

Three domains each produced RDF from their silver tables. The design had four weaknesses,
and each one is a drift on the [side-by-side table](semantic-drift.md#the-drifts-and-the-fixes).

**Shared ontology: four copies.** The published ontology in `docs/` (365 lines) and
three per-domain test copies (78, 72 and 70 lines) disagreed. The published copy said
`fintech:riskCustomer`, `fintech:accountCustomer`, `fintech:email` and `fintech:name`.
The producers wrote `forCustomer`, `accountOwner`, `customerEmail` and `customerName`.

**Identity: one rule, three copies, 32 bits.** Customer IRIs came from
`SHA-256(email | kyc_id)` truncated to 8 hex characters. The rule was implemented in:

- `domains/accounts/src/main/python/semantic/iri_resolver.py`
- `domains/risk-compliance/src/main/python/semantic/cross_domain_resolver.py`
- `domains/transactions/src/main/python/semantic/cross_domain_resolver.py`

Each copy's tests checked only that copy, so the three could drift apart and CI would
still pass.

**Typed values: `fintech:decimal` and `float`.** Balances and amounts were built from
Python `float` and typed `fintech:decimal`, a datatype the ontology never defined. `SUM`
over them fails.

**Validation: none.** No SHACL shapes existed. Nothing checked a producer's output
against the core before it was written.

There were also two churn queries: one under `domains/federation/queries/` and a copy in
`docs/`. The copy selected `?ticketCount`, which no pattern bound.

## What it does wrong, in numbers

These are the outputs of the demos run against the before code.

| Check | Result |
|---|---|
| Consumer query from the published core (`riskCustomer`) | `0 row(s)`, no error |
| Two customers, `customer111830@example.com`/`KYC0111830` and `customer130865@example.com`/`KYC0130865` | both mint `customer#15e5a0c2` |
| Birthday-bound collision odds, 77,000 customers, 32 bits | 49.85% |
| `SUM` over transaction amounts | `SPARQLTypeError`, not a number |
| Shapes validation of before output | `Conforms: False`, 11 identity and 22 type violations |

## Run the before demos

```bash
make semantic-drift-demo        # on the current branch, runs before and after side by side
```

The demos run the frozen before code from `examples/semantic-drift/before/` and the
current after code on the same data, so the before results appear in every run. The
output above is from `demo_empty_join.py`, `demo_identity_collision.py`,
`demo_decimal_sum.py` and `demo_shacl_catches_drift.py`.

For the full list of what each file shows, see
[`examples/semantic-drift/before/README.md`](https://github.com/naren-chakraview/chakraview-fintech-data-mesh/blob/main/examples/semantic-drift/before/README.md).
