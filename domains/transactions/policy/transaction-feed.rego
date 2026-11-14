# Domain policy for transactions/transaction-feed. Owned by the transactions domain (see CODEOWNERS).
# The platform guardrails in platform/governance/opa-policies/guardrails.rego still apply:
# this file can add restrictions, and it cannot allow what the platform denies.
package data_mesh.domain["transactions"]["transaction-feed"]

import rego.v1

default allow := false

allow if {
	input.action in {"read", "request_access"}
	input.principal.roles[_] in {"analyst", "risk_analyst", "fraud_analyst"}
}

# The product's approval_required flag from its YAML. The boundary still needs a grant.
requires_approval if input.product.approval_required == true

# Columns this domain shows. Anything not listed is masked (full_hash).
column_strategy := {"account_id": "hash_mask", "account_holder_name": "hash_mask", "amount": "no_mask", "merchant_id": "no_mask", "merchant_category_code": "no_mask"}
