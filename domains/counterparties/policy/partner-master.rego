# Domain policy for counterparties/partner-master. Owned by the counterparties domain (see CODEOWNERS).
# The platform guardrails in platform/governance/opa-policies/guardrails.rego still apply:
# this file can add restrictions, and it cannot allow what the platform denies.
package data_mesh.domain["counterparties"]["partner-master"]

import rego.v1

default allow := false

allow if {
	input.action in {"read", "request_access"}
	input.principal.roles[_] in {"analyst", "risk_analyst"}
}

# The product's approval_required flag from its YAML. The boundary still needs a grant.
requires_approval if input.product.approval_required == true

# Columns this domain shows. Anything not listed is masked (full_hash).
column_strategy := {}
