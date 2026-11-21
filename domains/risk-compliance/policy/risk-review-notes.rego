# Domain policy for risk-compliance/risk-review-notes. Owned by the risk-compliance domain (see CODEOWNERS).
# The platform guardrails still apply: this file can add restrictions, and it cannot allow what they deny.
#
# Agents propose review notes; a Risk owner accepts, rejects or rolls them back. An agent is never an
# approver: the platform denies owner actions to any delegated call.
package data_mesh.domain["risk-compliance"]["risk-review-notes"]

import rego.v1

risk_roles := {"analyst", "risk_analyst", "fraud_analyst"}

# Reads of the authoritative notes, by a risk analyst.
default allow := false

allow if {
	input.action == "read"
	input.principal.roles[_] in risk_roles
}

# A proposal is made by an agent acting for a risk analyst.
default allow_propose := false

allow_propose if {
	input.action == "propose"
	input.principal.roles[_] in risk_roles
}

# Identifiers and the band are shown. The note text is confidential, so the platform floor masks it (full_hash);
# this domain cannot show it in the clear.
column_strategy := {
	"note_id": "no_mask",
	"customer_iri": "no_mask",
	"risk_band": "no_mask",
}

# The agents that may propose. The risk-review agent is the only one.
allow_agents := ["spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent"]

# Columns an agent may ask for. A proposal asks for none; it carries its content in the payload.
agent_columns := []

# Accept, reject and roll back: the Risk domain owner, for a product the owner owns.
default allow_owner_actions := false

allow_owner_actions if {
	input.principal.roles[_] == "data_owner"
	input.product.owner == input.principal.owns[_]
}

# Reads and proposals of these notes need a grant (the product is confidential). The grant names the workload
# that calls, so a proposal needs a grant made for the agent, and a read needs one made for the person's workload.
