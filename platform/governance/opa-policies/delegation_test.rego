package data_mesh.delegation_test

import rego.v1

import data.data_mesh.access
import data.data_mesh.guardrails

AGENT := "spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent"
OTHER_AGENT := "spiffe://chakracommerce.com/ns/agents/sa/other-agent"
NOTEBOOK := "spiffe://chakracommerce.com/ns/analytics/sa/notebook"

analyst := {"subject": "risk.analyst@chakra.fintech", "roles": ["risk_analyst"], "owns": []}
owner := {"subject": "owner@risk-compliance.chakra.fintech", "roles": ["data_owner"], "owns": ["risk-compliance-domain"]}

risk_scores := {"id": "risk-compliance.risk-scores", "domain": "risk-compliance", "name": "risk-scores",
	"owner": "risk-compliance-domain", "classification": "sensitive", "approval_required": true}
review_notes := {"id": "risk-compliance.risk-review-notes", "domain": "risk-compliance", "name": "risk-review-notes",
	"owner": "risk-compliance-domain", "classification": "confidential", "approval_required": true}
account_master := {"id": "accounts.account-master", "domain": "accounts", "name": "account-master",
	"owner": "accounts-domain", "classification": "pii", "approval_required": true}

chain := [AGENT]

delegation := {"actor": AGENT, "chain": chain}

delegated_read(product, columns) := {
	"action": "read",
	"principal": analyst,
	"workload": {"spiffe_id": AGENT},
	"product": product,
	"delegation": delegation,
	"columns": columns,
}

# --- A delegated read: the intersection of the person, the agent and the product ---

test_agent_reads_columns_its_domain_lists if {
	access.allow with input as delegated_read(risk_scores, ["customer_iri", "risk_band", "scored_at"])
}

test_agent_cannot_read_a_column_only_the_person_can(
) if {
	not access.allow with input as delegated_read(risk_scores, ["customer_iri", "fraud_score"])
}

test_agent_not_named_by_the_domain_is_refused if {
	not access.allow with input as object.union(delegated_read(risk_scores, ["risk_band"]),
		{"delegation": {"actor": OTHER_AGENT, "chain": [OTHER_AGENT]}, "workload": {"spiffe_id": OTHER_AGENT}})
}

test_person_without_delegation_keeps_full_read if {
	access.allow with input as {"action": "read", "principal": analyst, "workload": {"spiffe_id": NOTEBOOK},
		"product": risk_scores, "columns": ["fraud_score", "kyc_verdict"]}
}

test_personal_product_refuses_agent_not_named_by_domain if {
	not access.allow with input as object.union(delegated_read(account_master, ["account_id"]),
		{"principal": {"subject": "x", "roles": ["analyst"], "owns": []}})
		with data.data_mesh.domain["accounts"]["account-master"].allow as true
}

test_personal_product_named_agent_is_allowed_by_domain_opt_in if {
	access.allow with input as object.union(delegated_read(account_master, ["account_id"]),
		{"principal": {"subject": "x", "roles": ["analyst"], "owns": []}})
		with data.data_mesh.domain["accounts"]["account-master"].allow as true
		with data.data_mesh.domain["accounts"]["account-master"].allow_agents as [AGENT]
		with data.data_mesh.domain["accounts"]["account-master"].agent_columns as ["account_id"]
}

test_agent_on_a_non_personal_product_is_refused_without_opt_in if {
	not access.allow with input as delegated_read(risk_scores, ["risk_band"])
		with data.data_mesh.domain["risk-compliance"]["risk-scores"].allow_agents as []
}

test_chain_deeper_than_the_cap_is_refused if {
	deep := ["spiffe://x/a", "spiffe://x/b", AGENT]
	not guardrails.platform_allow with input as object.union(delegated_read(risk_scores, ["risk_band"]),
		{"delegation": {"actor": AGENT, "chain": deep}})
}

test_chain_at_the_cap_is_allowed if {
	guardrails.platform_allow with input as object.union(delegated_read(risk_scores, ["risk_band"]),
		{"delegation": {"actor": AGENT, "chain": ["spiffe://x/a", AGENT]}, "lineage_verified": true})
}

# --- Masking: a delegated read never shows personal data in the clear ---

test_delegated_personal_column_is_fully_hashed if {
	access.masking_strategy == "full_hash" with input as {"column": "account_id", "product": account_master,
		"column_classification": "pii", "delegation": delegation}
		with data.data_mesh.domain["accounts"]["account-master"].column_strategy as {"account_id": "no_mask"}
}

test_person_personal_column_stays_partially_masked if {
	access.masking_strategy == "partial_mask" with input as {"column": "account_id", "product": account_master,
		"column_classification": "pii"}
}

# --- Proposals: only an agent proposes, and it is never an approver ---

test_agent_may_propose_for_an_analyst if {
	access.allow with input as {"action": "propose", "principal": analyst, "workload": {"spiffe_id": AGENT},
		"product": review_notes, "delegation": delegation, "columns": []}
		with data.data_mesh.domain["risk-compliance"]["risk-review-notes"].allow_agents as [AGENT]
}

test_person_without_delegation_may_not_propose if {
	not access.allow with input as {"action": "propose", "principal": analyst, "workload": {"spiffe_id": NOTEBOOK},
		"product": review_notes}
		with data.data_mesh.domain["risk-compliance"]["risk-review-notes"].allow_agents as [AGENT]
}

test_agent_not_named_may_not_propose if {
	not access.allow with input as {"action": "propose", "principal": analyst, "workload": {"spiffe_id": OTHER_AGENT},
		"product": review_notes, "delegation": {"actor": OTHER_AGENT, "chain": [OTHER_AGENT]}, "columns": []}
		with data.data_mesh.domain["risk-compliance"]["risk-review-notes"].allow_agents as [AGENT]
}

# --- Owner actions: the owner's own token only; an agent can never accept ---

test_owner_may_accept_for_an_owned_product if {
	access.allow with input as {"action": "accept", "principal": owner, "workload": {"spiffe_id": NOTEBOOK},
		"product": review_notes}
}

test_owner_action_needs_no_grant if {
	not access.requires_approval with input as {"action": "accept", "principal": owner,
		"workload": {"spiffe_id": NOTEBOOK}, "product": review_notes}
}

test_agent_cannot_accept_even_when_the_owner_is_delegated_through if {
	not access.allow with input as {"action": "accept", "principal": owner, "workload": {"spiffe_id": AGENT},
		"product": review_notes, "delegation": delegation}
}

test_agent_cannot_reject_or_roll_back_either if {
	not guardrails.platform_owner_allow with input as {"action": "rollback", "principal": owner,
		"workload": {"spiffe_id": AGENT}, "delegation": delegation}
	not guardrails.platform_owner_allow with input as {"action": "reject", "principal": owner,
		"workload": {"spiffe_id": AGENT}, "delegation": delegation}
}

test_analyst_cannot_accept_for_an_owner_domain if {
	not access.allow with input as {"action": "accept", "principal": analyst, "workload": {"spiffe_id": NOTEBOOK},
		"product": review_notes}
}

test_owner_of_another_domain_cannot_accept if {
	not access.allow with input as {"action": "accept",
		"principal": {"subject": "o@accounts", "roles": ["data_owner"], "owns": ["accounts-domain"]},
		"workload": {"spiffe_id": NOTEBOOK}, "product": review_notes}
}

# --- Delegation must name a SPIFFE actor ---

test_delegation_with_a_non_spiffe_actor_is_refused if {
	not guardrails.delegation_ok with input as {"delegation": {"actor": "analyst", "chain": ["analyst"]}}
}

# --- Aggregates: counts per group, which an agent may get for the columns the domain lists for aggregates ---

aggregate(product, columns) := {
	"action": "aggregate",
	"principal": analyst,
	"workload": {"spiffe_id": AGENT},
	"product": product,
	"delegation": delegation,
	"columns": columns,
}

test_agent_may_aggregate_a_listed_column if {
	access.allow with input as aggregate(risk_scores, ["risk_band"])
}

test_agent_may_not_aggregate_an_unlisted_column if {
	not access.allow with input as aggregate(risk_scores, ["fraud_score"])
}

test_agent_may_not_read_a_column_it_may_aggregate if {
	not access.allow with input as object.union(delegated_read(risk_scores, ["risk_band"]), {"action": "read", "columns": ["risk_band"]})
		with data.data_mesh.domain["risk-compliance"]["risk-scores"].agent_columns as []
}

test_person_may_aggregate_without_delegation if {
	access.allow with input as {"action": "aggregate", "principal": analyst, "workload": {"spiffe_id": NOTEBOOK},
		"product": risk_scores, "columns": ["fraud_score"]}
}

test_agent_not_named_may_not_aggregate if {
	not access.allow with input as object.union(aggregate(risk_scores, ["risk_band"]),
		{"delegation": {"actor": OTHER_AGENT, "chain": [OTHER_AGENT]}, "workload": {"spiffe_id": OTHER_AGENT}})
}

# --- Write tiers (addendum W2): who decided the data decides whether a human gate applies ---

write(kind, classification, caller, producer, subject_or_grant) := {
	"action": "write",
	"principal": analyst,
	"workload": {"spiffe_id": AGENT},
	"product": review_notes,
	"write": {"kind": kind, "classification": classification, "caller": caller, "producer": producer,
		"subject_or_grant": subject_or_grant},
}

test_captured_by_a_service_is_direct if {
	data.data_mesh.access.write_outcome == "direct" with input as write("captured", "pii", "service", false, false)
}

test_captured_by_an_agent_for_its_subject_is_direct if {
	data.data_mesh.access.write_outcome == "direct" with input as write("captured", "pii", "agent", false, true)
}

test_captured_by_an_agent_for_someone_else_is_forbidden if {
	data.data_mesh.access.write_outcome == "forbidden" with input as write("captured", "pii", "agent", false, false)
}

test_derived_public_or_internal_is_direct_for_an_agent if {
	data.data_mesh.access.write_outcome == "direct" with input as write("derived", "internal", "agent", false, false)
	data.data_mesh.access.write_outcome == "direct" with input as write("derived", "public", "agent", false, false)
}

test_derived_confidential_by_an_agent_needs_an_owner if {
	data.data_mesh.access.write_outcome == "requires_owner_review" with input as write("derived", "confidential", "agent", false, false)
	data.data_mesh.access.write_outcome == "requires_owner_review" with input as write("derived", "sensitive", "agent", false, false)
}

test_derived_confidential_by_a_listed_producer_is_direct if {
	data.data_mesh.access.write_outcome == "direct" with input as write("derived", "sensitive", "service", true, false)
}

test_derived_confidential_by_an_unlisted_service_is_forbidden if {
	data.data_mesh.access.write_outcome == "forbidden" with input as write("derived", "confidential", "service", false, false)
}

test_derived_pii_by_an_agent_is_refused if {
	data.data_mesh.access.write_outcome == "refused_pii" with input as write("derived", "pii", "agent", false, false)
}

test_derived_pii_by_a_listed_producer_is_direct if {
	data.data_mesh.access.write_outcome == "direct" with input as write("derived", "pii", "service", true, false)
}

test_a_domain_may_only_be_stricter_than_the_platform if {
	# The platform says requires_owner_review for a confidential derived write by an agent. A domain that says
	# direct cannot loosen it.
	data.data_mesh.access.write_outcome == "requires_owner_review"
		with input as write("derived", "confidential", "agent", false, false)
		with data.data_mesh.domain["risk-compliance"]["risk-review-notes"].write_outcome as "direct"
}

test_a_domain_can_tighten_the_platform if {
	data.data_mesh.access.write_outcome == "forbidden"
		with input as write("derived", "internal", "agent", false, false)
		with data.data_mesh.domain["risk-compliance"]["risk-review-notes"].write_outcome as "forbidden"
}

test_a_write_needs_a_domain_that_allows_it if {
	not data.data_mesh.access.allow with input as write("derived", "internal", "agent", false, false)
}

intake := {"id": "accounts.customer-intake", "domain": "accounts", "name": "customer-intake",
	"classification": "pii", "approval_required": true}

test_kyc_purpose_uses_the_kyc_masking_for_a_listed_column if {
	access.masking_strategy == "partial_mask" with input as {"column": "ssn", "product": intake,
		"column_classification": "pii", "purpose": "kyc"}
		with data.data_mesh.domain["accounts"]["customer-intake"].kyc_column_strategy as {"ssn": "partial_mask"}
		with data.data_mesh.domain["accounts"]["customer-intake"].column_strategy as {"ssn": "full_mask"}
}

test_the_default_purpose_keeps_the_full_mask if {
	access.masking_strategy == "full_mask" with input as {"column": "ssn", "product": intake,
		"column_classification": "pii", "purpose": "review"}
		with data.data_mesh.domain["accounts"]["customer-intake"].kyc_column_strategy as {"ssn": "partial_mask"}
		with data.data_mesh.domain["accounts"]["customer-intake"].column_strategy as {"ssn": "full_mask"}
}
