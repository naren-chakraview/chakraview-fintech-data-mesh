# Frozen "before": agents as they were at `agents-before`

This is the code at commit `b6dd9ea` (tag `agents-before`), frozen before the agent fix. Nothing in the platform
imports it. The files are byte-for-byte the tagged versions. `demo_*.py` load them to show the "before" column.

The boundary package (`platform/boundary/`), its OPA policies (`platform/governance/opa-policies/`), the risk-scores
domain policy, the product files and fixtures, and the accounts `RdfWriter` are all frozen here. The shared
libraries they import (identity, grants, masking, lineage verification) are live.

**D1, an agent has no identity of its own.** The boundary has no notion of delegation. An agent can present only the
analyst's token and its own certificate, and a claimed `X-ZT-Verified-*` header is ignored rather than refused. Shown
in `platform/boundary/main.py` (`get_caller` verifies the bearer token and the client certificate, nothing more) and
`platform/boundary/pipeline.py` (`_base_input` has no delegation field). Demos: `demo_actor_must_be_proven.py`,
`demo_agent_is_the_person.py`.

**D2, an agent gets the person's whole view.** Policy input describes one principal and one workload, so the
agent is the analyst's notebook. The domain policy has no agent capability. Shown in
`platform/governance/opa-policies/guardrails.rego` and `abac.rego` (no agent rules),
`domains/risk-compliance/policy/risk-scores.rego` (roles only). Demo: `demo_agent_capability.py`.

**D3, no governed write path.** The boundary is read-only, and the only write code (`write_to_jena`, in
`domains/accounts/src/main/python/semantic/rdf_writer.py`) posts to Fuseki's `/update`, which the trust fix removed.
Nothing calls it. Demo: `demo_agent_proposes.py`.

**D4, lineage cannot name a delegator.** A signed statement records the producing workload only, as built by
`platform/lineage/attest.py` (`build_statement`: producer, code commit, inputs, run time). Demo:
`demo_agent_proposes.py`.

**D5, the audit has no chain.** Each record names the person and the workload, and nothing links a write to the reads
behind it. Shown in `platform/boundary/pipeline.py` (the read audit `extra_audit`). Demo: `demo_agent_is_the_person.py`.

**Undo.** There is no rollback route and no version history. Shown in `platform/boundary/main.py` (the route list).
Demo: `demo_undo.py`.
