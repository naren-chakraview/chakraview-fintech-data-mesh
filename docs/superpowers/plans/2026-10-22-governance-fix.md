# Governance Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the fintech-data-mesh governance run in code: Rego policies that load on OPA 1.x, OPA wired into compose, fail-closed masking in Python, access requests evaluated by OPA, and masked-and-audited reads.

**Architecture:** Policies live in `platform/governance/opa-policies/` and are tested with `opa test`. OPA runs in compose and Helm with those policies mounted. The discovery backend calls OPA over HTTP for access decisions. A read helper asks OPA for a masking strategy per column, applies it with `DataMasker`, and writes an audit record to Elasticsearch. Every failure path denies or masks.

**Tech Stack:** OPA 1.0.0 (Rego v1), Python 3.12, FastAPI 0.104.0, httpx (new pinned dependency), pytest 7.4.0, Docker Compose, Elasticsearch 8.11.0.

**Spec:** `docs/reviews/governance-fix-brief.md` (with `docs/reviews/abac.rego` and `docs/reviews/abac_test.rego`)

## Global Constraints

- OPA version is pinned to `1.0.0` everywhere: compose, Helm values, CI. Never `latest`.
- Rego uses `import rego.v1`; rules use `if` and `contains`.
- Default masking strategy is `full_hash`. Default access decision is `allow := false`.
- Any OPA failure (transport error, non-200, malformed body) means deny, never a default value.
- Role names are the docs' names: `analyst`, `risk_analyst`, `external_analyst`, `contractor`, `data_owner`, `customer_privacy_officer`.
- OPA listens on `8181`. The `8282` mapping is removed.
- Policy path is `data_mesh/access`. Masking strategy path is `data_mesh/access/masking_strategy`.

## Review Focus

1. OPA unreachable, returns non-200, or returns a body without `result` → access request is denied and no rows are returned. (Task 4, Task 5)
2. A classification value that is not one of `public|sensitive|confidential|pii|restricted` (for example `PII`, `Public`, `""`) → masked. (Task 1, Task 3)
3. A product with no column classifications → treated as `restricted`, so a request goes to `pending`, never `approved`. (Task 4)
4. An OPA masking strategy name that `DataMasker` does not know → `ValueError`, never the raw value. (Task 3)
5. Audit write failure → no rows returned from the read helper. (Task 5)

## Open Decisions (defaults used in this plan)

- **Fraud role:** docs use both `fraud_analyst` (4 hits) and `fraud-team` (6 hits); the new Rego has no fraud role. Default: `fraud_analyst` is not granted read in `abac.rego`, so it falls to the same deny and masking defaults as any unlisted role. Confirm before Task 1 if fraud analysts should read `sensitive` data without approval.
- **Product classification:** `DataProduct` has no `data_classification` field. Default: product classification is the highest column classification in `access_policy.columns`, ordered `public < sensitive < confidential < pii < restricted`; no columns → `restricted`.
- **CI:** the repo has no `.github/workflows/`. Default: add one workflow that runs `make policy-test` with OPA 1.0.0.
- **Helm:** `helm/` has only values files and no chart templates, so nothing mounts policies into Kubernetes. Default: pin the image in the three values files only. Mounting policies needs a ConfigMap template, which is out of scope here.
- **Deny response:** default is to store the request with status `denied` and return HTTP 503.
- **Stale policy paths in docs:** `docs/platform/discovery.md:500` and `docs/production/troubleshooting.md` use `authz/...` paths. Default: change them to `data_mesh/access`.

---

## Task 1: Rego policies for OPA 1.x

**Files:**
- Modify: `platform/governance/opa-policies/abac.rego` (replace with `docs/reviews/abac.rego`)
- Modify: `platform/governance/opa-policies/compliance.rego`
- Create: `platform/governance/opa-policies/abac_test.rego` (copy of `docs/reviews/abac_test.rego`)
- Create: `platform/governance/opa-policies/compliance_test.rego`

**Interfaces:**
- Consumes: none
- Produces: package `data_mesh.access` with rules `allow`, `requires_approval`, `masking_strategy` (input keys: `action`, `user_role`, `data_classification`, `column_classification`); package `data_mesh.compliance` with `enforce_retention` and `enforce_masking` as sets of violation objects (input keys: `table`, `table_retention_days`, `column`, `column_classification`, `is_masked`).

- [ ] **Step 1: Copy the new policy and its tests into place**

Copy `docs/reviews/abac.rego` over `platform/governance/opa-policies/abac.rego`, and copy `docs/reviews/abac_test.rego` to `platform/governance/opa-policies/abac_test.rego`. Leave the `docs/reviews/` copies in place as the review record.

- [ ] **Step 2: Write the failing compliance tests**

Create `platform/governance/opa-policies/compliance_test.rego`:

```rego
package data_mesh.compliance_test

import rego.v1

import data.data_mesh.compliance

test_retention_under_one_year_violates if {
	count(compliance.enforce_retention) == 1 with input as {"table": "t", "table_retention_days": 180}
}

test_retention_one_year_passes if {
	count(compliance.enforce_retention) == 0 with input as {"table": "t", "table_retention_days": 365}
}

test_unmasked_pii_column_violates if {
	count(compliance.enforce_masking) == 1 with input as {"table": "t", "column": "account_id", "column_classification": "pii", "is_masked": false}
}

test_masked_pii_column_passes if {
	count(compliance.enforce_masking) == 0 with input as {"table": "t", "column": "account_id", "column_classification": "pii", "is_masked": true}
}

test_unmasked_public_column_passes if {
	count(compliance.enforce_masking) == 0 with input as {"table": "t", "column": "merchant_id", "column_classification": "public", "is_masked": false}
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `docker run --rm -v "$PWD/platform/governance/opa-policies:/p" openpolicyagent/opa:1.0.0 test /p -v`
Expected: FAIL; the compliance tests error on `compliance.rego` (old syntax, no `if`/`contains`).

- [ ] **Step 4: Port `compliance.rego` to OPA 1.x**

Rewrite with `import rego.v1`:
- `enforce_retention contains violation if { input.table_retention_days < 365; violation := {...} }` with the same message and fields as today.
- `enforce_masking contains violation if { input.column_classification == "pii"; not input.is_masked; violation := {...} }`. This replaces the hard-coded column list. The violation object keeps `message`, `column`, `table`.
- `audit_required if true`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker run --rm -v "$PWD/platform/governance/opa-policies:/p" openpolicyagent/opa:1.0.0 test /p -v`
Expected: PASS; 6 `abac` tests and 5 `compliance` tests pass. Then run `docker run --rm -v "$PWD/platform/governance/opa-policies:/p" openpolicyagent/opa:1.0.0 check --strict /p` and expect no output.

- [ ] **Step 6: Commit**

```bash
git add platform/governance/opa-policies/
git commit -m "fix: port governance Rego to OPA 1.x and fail closed on masking"
```

---

## Task 2: Wire OPA into compose, Helm, Makefile, and CI

**Files:**
- Modify: `docker-compose.yml:108-113` (the `opa` service)
- Modify: `helm/values-aws-eks.yaml:85-87`, `helm/values-gcp-gke.yaml:88-90`, `helm/values-azure-aks.yaml:90-92` (the `opa.image` lines)
- Modify: `Makefile` (add `policy-test` target and `.PHONY` entry)
- Create: `.github/workflows/policy-test.yml`

**Interfaces:**
- Consumes: `platform/governance/opa-policies/` from Task 1
- Produces: `make policy-test` target; OPA HTTP API on `localhost:8181` with the policies loaded from `/policies`

- [ ] **Step 1: Verify the current compose service fails to serve policies**

Run: `docker compose config --services | grep -x opa && docker compose config | grep -A3 "opa:" | grep -c policies`
Expected: prints `0`. The current service has no policy volume.

- [ ] **Step 2: Replace the `opa` service in `docker-compose.yml`**

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

- [ ] **Step 3: Pin the image in the three Helm values files**

Change `image: openpolicyagent/opa:latest` to `image: openpolicyagent/opa:1.0.0` in each of the three files listed above.

- [ ] **Step 4: Add the `policy-test` Makefile target**

Add `policy-test` to `.PHONY`, plus:

```make
policy-test:
	opa test platform/governance/opa-policies -v
```

Use the locally installed OPA 1.0.0 binary; the Docker form from Task 1 is an alternative.

- [ ] **Step 5: Add the CI workflow**

Create `.github/workflows/policy-test.yml`, triggered on `push` and `pull_request`. Its job checks out the repo, installs OPA 1.0.0 (pinned version, not latest), and runs `make policy-test`.

- [ ] **Step 6: Verify compose serves the policies**

Run: `docker compose config --quiet && docker compose up -d opa && curl -s -X POST localhost:8181/v1/data/data_mesh/access -H 'Content-Type: application/json' -d '{"input":{"action":"read","user_role":"analyst","data_classification":"public"}}'`
Expected: `config` exits 0; the curl output includes `"allow":true`.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml helm/ Makefile .github/workflows/policy-test.yml
git commit -m "infra: load governance policies into OPA 1.0.0 in compose, Helm and CI"
```

---

## Task 3: Fail-closed masking in Python

**Files:**
- Modify: `shared/compliance/masking.py` (`ColumnMaskingPolicy.should_mask` at line 66; `DataMasker` at lines 5-42)
- Create: `tests/unit/test_masking.py`

**Interfaces:**
- Consumes: none
- Produces:
  - `ColumnMaskingPolicy.should_mask(table: str, column: str) -> bool`: `True` unless the column is classified exactly `"public"`.
  - `DataMasker.full_hash(value: str) -> str`: lowercase SHA-256 hex digest of `value`, matching the `full_hash` example in `docs/platform/governance.md`.
  - `DataMasker.apply(strategy: str, value: str) -> str`: dispatches `no_mask`, `full_hash`, `hash_mask`, `partial_mask`, `full_mask`. Raises `ValueError` for any other name.

- [ ] **Step 1: Write the failing tests**

```python
import hashlib

import pytest

from shared.compliance.masking import ColumnMaskingPolicy, DataMasker


def test_unclassified_column_is_masked():
    policy = ColumnMaskingPolicy()
    assert policy.should_mask("transactions.raw_transactions", "unknown_col") is True


def test_public_column_is_not_masked():
    policy = ColumnMaskingPolicy()
    policy.add_policy("t", "merchant_id", "public")
    assert policy.should_mask("t", "merchant_id") is False


@pytest.mark.parametrize("classification", ["PUBLIC", "Public", "", "pii"])
def test_non_exact_public_is_masked(classification):
    policy = ColumnMaskingPolicy()
    policy.add_policy("t", "c", classification)
    assert policy.should_mask("t", "c") is True


def test_full_hash_is_sha256_hex():
    assert DataMasker.full_hash("John Doe") == hashlib.sha256(b"John Doe").hexdigest()


def test_apply_known_strategy():
    assert DataMasker.apply("no_mask", "abc") == "abc"


def test_apply_unknown_strategy_raises():
    with pytest.raises(ValueError):
        DataMasker.apply("show_everything", "4111111111111111")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_masking.py -v`
Expected: FAIL; `should_mask` returns `False` for unclassified columns, and `full_hash` and `apply` do not exist.

- [ ] **Step 3: Implement the changes in `shared/compliance/masking.py`**

- `should_mask`: `return self.get_column_classification(table, column) != "public"`.
- Add `full_hash` as a `@staticmethod`: `hashlib.sha256(value.encode()).hexdigest()`.
- Add `apply` as a `@staticmethod`: a dict maps each strategy name to its method; a missing key raises `ValueError(f"unknown masking strategy: {strategy}")`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_masking.py -v`
Expected: PASS, 8 tests (including the parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add shared/compliance/masking.py tests/unit/test_masking.py
git commit -m "fix: mask unclassified columns and reject unknown masking strategies"
```

---

## Task 4: Evaluate access requests with OPA

**Files:**
- Create: `platform/discovery/backend/opa_client.py`
- Modify: `platform/discovery/backend/main.py:127-149` (`request_access`)
- Modify: `requirements.txt` (add `httpx` pinned to a version that works with `fastapi==0.104.0`)
- Create: `tests/unit/test_access_requests.py`

**Interfaces:**
- Consumes: `data_mesh/access` rules from Task 1; OPA at `OPA_URL` (default `http://opa:8181/v1/data/data_mesh/access`)
- Produces:
  - `class OPAError(Exception)`
  - `async def evaluate_access(user_id: str, user_role: str, action: str, data_classification: str) -> dict`: returns `{"allow": bool, "requires_approval": bool}`. Raises `OPAError` on transport error, non-200, a body without `result`, or non-boolean `allow` / `requires_approval`. Timeout 2 seconds.
  - `def product_classification(product: DataProduct) -> str`: highest column classification by the ordering in Open Decisions; `"restricted"` when there are no columns or a value is unknown.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_access_requests.py`, use FastAPI's `TestClient` and `monkeypatch` the `evaluate_access` name in `main`. Look up a public-only product and a product with a `pii` column in the sample data loaded by `main.py`. Cover:

- `test_public_read_is_approved`: stub returns `{"allow": True, "requires_approval": False}`, the public product, `user_role` `analyst`; response `status == "approved"`.
- `test_pii_product_is_pending_with_owner_and_sla`: stub returns `{"allow": False, "requires_approval": True}`, the pii product; response `status == "pending"`, `routed_to == product.owner`, `approval_sla_hours == product.access_policy.approval_sla_hours`.
- `test_opa_error_denies_request`: stub raises `OPAError`; response status code 503; the stored request has `status == "denied"`.
- `test_product_without_columns_is_classified_restricted`: product with `access_policy.columns == []`; the stub records its arguments and returns `{"allow": True, "requires_approval": True}`. Assert the recorded `data_classification == "restricted"` and the response `status == "pending"`.

For the `opa_client` module itself, add `test_evaluate_access_raises_on_non_200` and `test_evaluate_access_raises_on_missing_result` using `httpx.MockTransport`, pointing the client at a mock.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_access_requests.py -v`
Expected: FAIL; `opa_client` does not exist and the endpoint never calls OPA.

- [ ] **Step 3: Implement `opa_client.py`**

Implement `evaluate_access` with an `httpx.AsyncClient` (2-second timeout). The request body is `{"input": {"user_id": ..., "user_role": ..., "action": ..., "data_classification": ...}}`. Validate the response before returning. Implement `product_classification` as described in Open Decisions.

- [ ] **Step 4: Update `request_access` in `main.py`**

1. Look up the product by `data_product_id`; return 404 if missing.
2. Call `evaluate_access` with `data_classification=product_classification(product)`.
3. On `OPAError`: store the request with `status = "denied"`, then raise `HTTPException(503, "Policy engine unavailable; request denied")`.
4. Otherwise: status `approved` when `allow` and not `requires_approval`; otherwise `pending`.
5. For `pending`, include `routed_to = product.owner` and `approval_sla_hours = product.access_policy.approval_sla_hours` in the response.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_access_requests.py -v`
Expected: PASS for all cases listed in Step 1.

- [ ] **Step 6: Commit**

```bash
git add platform/discovery/backend/ requirements.txt tests/unit/test_access_requests.py
git commit -m "feat: evaluate discovery access requests with OPA and deny on errors"
```

---

## Task 5: Enforce masking on read, with audit

**Files:**
- Create: `platform/governance/enforce.py`
- Create: `tests/unit/test_enforce.py`

**Interfaces:**
- Consumes: `ColumnMaskingPolicy.get_column_classification` (existing); `DataMasker.apply` (Task 3); `OPAError` (Task 4)
- Produces:
  - `async def mask_rows(rows: list[dict], table: str, columns: list[str], user_id: str, user_role: str, policy: ColumnMaskingPolicy, *, decide_strategy: Callable[[str, str | None], Awaitable[str]], write_audit: Callable[[dict], Awaitable[None]]) -> list[dict]`
  - Default `decide_strategy` posts `{"input": {"user_role": ..., "column_classification": ...}}` to `OPA_URL` `.../data_mesh/access/masking_strategy` and returns `result`. Raises `OPAError` on any failure.
  - Default `write_audit` posts the record to `ES_URL` (default `http://elasticsearch:9200`) at index `governance-audit`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_enforce.py`, pass stub `decide_strategy` and `write_audit` callables. Cover:

- `test_unclassified_column_is_hashed_on_read`: policy has no classification for the column; stub returns `"full_hash"`; the masked value is `hashlib.sha256` of the original, not the raw value.
- `test_public_column_is_returned_unchanged`: stub returns `"no_mask"`.
- `test_one_audit_record_per_read`: a read of 3 rows writes exactly one audit dict containing `user_id`, `user_role`, `table`, `columns`, and `strategies`.
- `test_opa_error_returns_no_rows`: stub raises `OPAError`; the function raises and `write_audit` is never called.
- `test_audit_failure_returns_no_rows`: `write_audit` raises `RuntimeError`; the function raises and no rows are returned.
- `test_unknown_strategy_raises`: stub returns `"show_everything"`; `ValueError` propagates.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_enforce.py -v`
Expected: FAIL; `platform/governance/enforce.py` does not exist.

- [ ] **Step 3: Implement `enforce.py`**

For each column in `columns`, call `decide_strategy(user_role, policy.get_column_classification(table, column))`, then apply `DataMasker.apply(strategy, value)` to every row. Build the audit dict, call `write_audit` before returning, and return the masked rows. If anything raises, let the exception propagate; the function returns nothing in that case. Apply the audit write before returning rows, so a failed write denies the read.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_enforce.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add platform/governance/enforce.py tests/unit/test_enforce.py
git commit -m "feat: mask and audit governed reads through OPA"
```

---

## Task 6: Docs and role-name sweep

**Files:**
- Modify: `docs/platform/governance.md` (code sample around lines 337-400; fallback at line 399; examples near 567 use `fraud_analyst`)
- Modify: `docs/platform/discovery.md:500`
- Modify: `docs/production/troubleshooting.md:272, 449, 462`
- Modify: any other `docs/` file (excluding `docs/superpowers/`) that matches `internal-analyst|fraud-team|external-analyst|authz/`

**Interfaces:**
- Consumes: `mask_rows` (Task 5); role names from Task 1
- Produces: docs whose sample code calls the same paths and roles the code uses

- [ ] **Step 1: Find every stale reference**

Run: `grep -rnE "internal-analyst|fraud-team|external-analyst|authz/" docs --exclude-dir=superpowers`
Expected: the list of lines to change (at least `governance.md`, `discovery.md:500`, `troubleshooting.md:272,449,462`).

- [ ] **Step 2: Update the masking sample**

In `docs/platform/governance.md`, change the fallback in the sample at line 399 from `"no_mask"` to `"full_hash"`. Change the OPA call to `data_mesh/access/masking_strategy`. Replace the sample's raw query path with a call to `mask_rows`, so the example reads through the enforcement helper.

- [ ] **Step 3: Update the other paths and roles**

Replace `authz/` with `data_mesh/access` in the files from Step 1. Replace the old role names with the docs' names (`internal-analyst` → `analyst`, `external-analyst` → `external_analyst`, `fraud-team` → `fraud_analyst` per the Open Decisions).

- [ ] **Step 4: Verify**

Run: `grep -rnE "internal-analyst|fraud-team|external-analyst|authz/" docs --exclude-dir=superpowers`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "docs: point governance examples at enforced OPA paths and role names"
```

---

## Task 7: End-to-end verification

**Files:** none modified

- [ ] **Step 1: Policies pass in CI-equivalent form**

Run: `make policy-test`
Expected: all `abac` and `compliance` tests PASS.

- [ ] **Step 2: Python tests pass**

Run: `make test-unit`
Expected: all unit tests PASS, including `test_masking.py`, `test_access_requests.py`, and `test_enforce.py`.

- [ ] **Step 3: Stack serves decisions**

Run: `docker compose up -d opa && curl -s -X POST localhost:8181/v1/data/data_mesh/access -H 'Content-Type: application/json' -d '{"input":{"action":"read","user_role":"analyst","data_classification":"public"}}'`
Expected: response includes `"allow":true`.

- [ ] **Step 4: Check the brief's acceptance criteria**

- `opa check` and `opa test` pass in CI on OPA 1.0.0 (Step 1 and the workflow in Task 2).
- `docker compose up` loads the policies (Task 2, Step 6).
- An unclassified column comes back masked (Task 3 test, Task 5 test).
- An access request for a PII product returns `pending` with an owner and SLA; a public one for `analyst` returns `approved` (Task 4 tests).

- [ ] **Step 5: Confirm the tree**

Run: `git status --short`
Expected: only the intended files; `docs/reviews/` and `docs/superpowers/plans/2026-10-22-governance-fix.md` may remain untracked until you decide whether to commit them.

---

## Self-Review Notes

- Spec coverage: brief items 1-5 map to Tasks 1-5, the acceptance list maps to Task 7. Brief item 4 (role names) is handled by the replacement `abac.rego` (Task 1) plus the sweep (Task 6).
- Brief gaps found while planning: `DataProduct` has no `data_classification` (Task 4 derives it); `DataMasker` has no `full_hash` and no strategy dispatch (Task 3 adds both); `helm/` has no templates for OPA (Open Decisions); the repo has no CI config (Task 2 adds one); `authz/` paths in three docs (Task 6).
- Dependencies are sequential: Task 4 needs Task 1's rule names, Task 5 needs Tasks 3 and 4.
