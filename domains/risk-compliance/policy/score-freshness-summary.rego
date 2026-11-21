# Domain policy for risk-compliance/score-freshness-summary. Owned by the risk-compliance domain (see CODEOWNERS).
# The platform guardrails still apply: this file can add restrictions, and it cannot allow what they deny.
package data_mesh.domain["risk-compliance"]["score-freshness-summary"]

import rego.v1

risk_roles := {"analyst", "risk_analyst", "fraud_analyst"}

default allow := false

allow if {
	input.action in {"read", "aggregate", "request_access"}
	input.principal.roles[_] in risk_roles
}

# Writes: analysts, directly or through the risk-review agent acting for one. The columns an agent writes are the
# internal ones; customer_label (personal) is never written by an agent (the write-tier refusal).
default allow_write := false

allow_write if {
	input.action == "write"
	input.principal.roles[_] in risk_roles
}

allow_agents := ["spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent"]

agent_write_columns := ["summary_id", "day", "risk_band", "stale_count"]

column_strategy := {
	"summary_id": "no_mask",
	"day": "no_mask",
	"risk_band": "no_mask",
	"stale_count": "no_mask",
}

# Accept, reject and roll back: the domain owner, for a product the owner owns (addendum W2: the owner can roll back any
# write, and a rollback is signed and audited).
default allow_owner_actions := false

allow_owner_actions if {
	input.principal.roles[_] == "data_owner"
	input.product.owner == input.principal.owns[_]
}
