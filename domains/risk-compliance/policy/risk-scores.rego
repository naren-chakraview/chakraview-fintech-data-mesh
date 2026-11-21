# Domain policy for risk-compliance/risk-scores. Owned by the risk-compliance domain (see CODEOWNERS).
# The platform guardrails in platform/governance/opa-policies/guardrails.rego still apply:
# this file can add restrictions, and it cannot allow what the platform denies.
package data_mesh.domain["risk-compliance"]["risk-scores"]

import rego.v1

default allow := false

allow if {
	input.action in {"read", "aggregate", "request_access"}
	input.principal.roles[_] in {"analyst", "risk_analyst", "fraud_analyst"}
}

# The product's approval_required flag from its YAML. The boundary still needs a grant.
requires_approval if input.product.approval_required == true

# Writes: the listed producer (a risk service) writes the sensitive derived output. Agents never write it directly;
# the platform sends an agent's write to a proposal (the rule in the guardrails).
allow_write if {
	input.action == "write"
	input.principal.roles[_] == "risk_producer"
}

# Columns this domain shows. Anything not listed is masked (full_hash).
column_strategy := {
	"fraud_score": "partial_mask",
	"customer_iri": "no_mask",
	"risk_band": "no_mask",
	"scored_at": "no_mask",
	"account_ref": "partial_mask",
	"kyc_verdict": "partial_mask",
}

# The agents that may act for a person on this product. Only the risk-review agent, and only for the
# columns below: the pseudonymous customer IRI, the band and the score date. fraud_score and kyc_verdict
# stay with the person, so a grant for the person does not reach them through an agent.
allow_agents := ["spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent"]

agent_columns := ["customer_iri", "risk_band", "scored_at"]

# Columns an agent may group counts by. The band only: counts of it reveal no customer's row.
agent_aggregate_columns := ["risk_band"]
