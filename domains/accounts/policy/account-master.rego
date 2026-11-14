# Domain policy for accounts/account-master. Owned by the accounts domain (see CODEOWNERS).
# The platform guardrails in platform/governance/opa-policies/guardrails.rego still apply:
# this file can add restrictions, and it cannot allow what the platform denies.
package data_mesh.domain["accounts"]["account-master"]

import rego.v1

default allow := false

allow if {
	input.action in {"read", "request_access"}
	input.principal.roles[_] in {"analyst", "risk_analyst"}
}

# The product's approval_required flag from its YAML. The boundary still needs a grant.
requires_approval if input.product.approval_required == true

# Columns this domain shows. Anything not listed is masked (full_hash).
column_strategy := {"account_id": "partial_mask", "customer_name": "partial_mask", "balance": "partial_mask"}
