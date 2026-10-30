# Fix brief: fintech-data-mesh governance

**Repo:** `naren-chakraview/chakraview-fintech-data-mesh` at `0c925d0` (public `main`, re-checked 2026-10-22; the merge since `8e60a3f` added the semantic integration case study and rebuilt the site, and changed no governance code)
**Why now:** article 1 of the data mesh series links readers to this repo and describes its governance. Today the governance exists in the docs, not in running code.

## What is wrong

1. **The Rego policies do not load on any OPA version.** `platform/governance/opa-policies/abac.rego` and `compliance.rego` fail `opa check` on OPA 0.68 (the `in` keyword needs `import future.keywords.in`) and on OPA 1.0 (rule bodies need `if`, partial sets need `contains`). `docker-compose.yml` runs `openpolicyagent/opa:latest`, which is 1.x.
2. **OPA is never given the policies or called.** The compose service runs `run --server` with no policy volume, and maps `8282:8282` while OPA listens on 8181. No Python code calls OPA: `POST /api/access-requests` in `platform/discovery/backend/main.py` stores the request in memory with status `pending` and never evaluates it.
3. **Masking fails open.**
   - `shared/compliance/masking.py`, `ColumnMaskingPolicy.should_mask` returns `False` for a column with no classification, so an unclassified column is shown in the clear. `DataMasker` is also not used by any code path.
   - `abac.rego` masks only two hard-coded column names, and only for `external-analyst`.
   - The `get_masking_strategy` sample in `docs/platform/governance.md` (around line 399) defaults to `"no_mask"` when OPA returns nothing.
4. **Role names disagree.** The docs use `analyst`, `risk_analyst`, `external_analyst`, `contractor`, `data_owner`, `customer_privacy_officer`. The Rego uses `internal-analyst`, `fraud-team`, `external-analyst`. Pick the docs' names.
5. Minor: `input.data_sensitivity in ["public", "public"]` in `abac.rego` duplicates a value.

## Fixes

### 1. Rewrite the policies for OPA 1.x, failing closed (tested)

Replace `platform/governance/opa-policies/abac.rego` with the version in `abac.rego` next to this file, and add `abac_test.rego`. Both pass `opa check` and `opa test` on OPA 1.0.0 (6/6 tests). The key rules:

```rego
default allow := false
default requires_approval := false
default masking_strategy := "full_hash"   # unknown or missing classification is masked
masking_strategy := "no_mask" if input.column_classification == "public"
```

Port `compliance.rego` the same way (`import rego.v1`, `enforce_retention contains violation if { ... }`), and drive the PII check from `input.column_classification == "pii"` rather than a list of column names.

### 2. Wire OPA in compose

```yaml
  opa:
    image: openpolicyagent/opa:1.0.0
    container_name: chakra-opa
    command: ["run", "--server", "--addr=0.0.0.0:8181", "/policies"]
    ports:
      - "8181:8181"
    volumes:
      - ./platform/governance/opa-policies:/policies:ro
```

Do the same for the Helm values. Add a `make policy-test` target running `opa test platform/governance/opa-policies -v`, and run it in CI.

### 3. Fail closed in Python

```python
def should_mask(self, table: str, column: str) -> bool:
    """Mask everything except columns explicitly classified as public."""
    return self.get_column_classification(table, column) != "public"
```

In `docs/platform/governance.md`, change the sample's fallback to `"full_hash"`, and raise (deny) when the OPA call fails instead of returning a default.

### 4. Evaluate access requests

In `POST /api/access-requests`:
- call `POST http://opa:8181/v1/data/data_mesh/access` with `user_id`, `user_role`, `action`, and the product's `data_classification`;
- set the status to `approved` when `allow` is true and `requires_approval` is false, otherwise `pending`, routed to the product owner with the product's approval SLA;
- deny on any OPA error.

Add a test for each outcome.

### 5. Enforce on read (smallest honest version)

Add a query helper (for example `platform/governance/enforce.py`) that, before returning rows, asks OPA for `masking_strategy` per column and applies `DataMasker`, then writes one audit record (user, role, table, columns, strategies) to Elasticsearch. Use it in the documented example queries, so "masked on read and audited" is true of the code.

## Acceptance

- `opa check` and `opa test` pass in CI on a pinned OPA 1.x.
- `docker compose up` loads the policies; `curl localhost:8181/v1/data/data_mesh/access` returns a decision.
- An unclassified column comes back masked.
- An access request for a PII product returns `pending` with an owner and SLA; a public one for `analyst` returns `approved`.
