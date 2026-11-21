# Domain policy for risk-compliance/risk-scores. Owned by the risk-compliance domain (see CODEOWNERS).
# The platform guardrails in platform/governance/opa-policies/guardrails.rego still apply:
# this file can add restrictions, and it cannot allow what the platform denies.
package data_mesh.domain["risk-compliance"]["risk-scores"]

import rego.v1

default allow := false

allow if {
	input.action in {"read", "request_access"}
	input.principal.roles[_] in {"analyst", "risk_analyst", "fraud_analyst"}
}

# The product's approval_required flag from its YAML. The boundary still needs a grant.
requires_approval if input.product.approval_required == true

# Columns this domain shows. Anything not listed is masked (full_hash).
column_strategy := {
	"fraud_score": "partial_mask",
	"customer_iri": "no_mask",
	"risk_band": "no_mask",
	"scored_at": "no_mask",
}

# The agents that may act for a person on this product. Only the risk-review agent, and only for the
# columns below: the pseudonymous customer IRI, the band and the score date. fraud_score and kyc_verdict
# stay with the person, so a grant for the person does not reach them through an agent.
allow_agents := ["spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent"]

agent_columns := ["customer_iri", "risk_band", "scored_at"]
