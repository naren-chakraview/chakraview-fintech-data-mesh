package data_mesh.access_test

import rego.v1

import data.data_mesh.access

person := {"subject": "analyst@chakra.fintech", "roles": ["risk_analyst"]}
workload := {"spiffe_id": "spiffe://chakracommerce.com/ns/analytics/sa/notebook"}
risk_scores := {"id": "risk-compliance.risk-scores", "domain": "risk-compliance", "name": "risk-scores", "classification": "sensitive", "approval_required": true}
account_master := {"id": "accounts.account-master", "domain": "accounts", "name": "account-master", "classification": "pii", "approval_required": true}

read_request(product) := {"action": "read", "principal": person, "workload": workload, "product": product}

masking_input(column, classification) := {
	"action": "read",
	"principal": person,
	"workload": workload,
	"product": account_master,
	"column": column,
	"column_classification": classification,
}

test_verified_analyst_reads_risk_scores if {
	access.allow with input as read_request(risk_scores)
}

test_read_of_risk_scores_needs_approval if {
	access.requires_approval with input as read_request(risk_scores)
}

test_unauthenticated_read_is_denied if {
	not access.allow with input as object.union(read_request(risk_scores), {"principal": {"subject": "", "roles": ["risk_analyst"]}})
}

test_missing_workload_is_denied if {
	not access.allow with input as object.remove(read_request(risk_scores), ["workload"])
}

test_non_spiffe_workload_is_denied if {
	not access.allow with input as object.union(read_request(risk_scores), {"workload": {"spiffe_id": "https://example.com"}})
}

test_write_is_denied_on_read_path if {
	not access.allow with input as object.union(read_request(risk_scores), {"action": "write"})
}

test_product_without_domain_policy_is_denied if {
	not access.allow with input as read_request({"id": "x.y", "domain": "unknown", "name": "y", "classification": "public", "approval_required": false})
}

test_wrong_role_is_denied if {
	not access.allow with input as object.union(read_request(risk_scores), {"principal": {"subject": "x", "roles": ["external_analyst"]}})
}

test_pii_always_requires_approval_even_if_domain_says_no if {
	access.requires_approval with input as read_request(object.union(account_master, {"approval_required": false}))
		with data.data_mesh.domain["accounts"]["account-master"].requires_approval as false
}

test_domain_cannot_loosen_platform_allow if {
	not access.allow with input as object.union(read_request(risk_scores), {"principal": {"subject": "", "roles": ["risk_analyst"]}})
		with data.data_mesh.domain["risk-compliance"]["risk-scores"].allow as true
}

test_pii_column_is_partially_masked if {
	access.masking_strategy == "partial_mask" with input as masking_input("account_id", "pii")
}

test_domain_cannot_unmask_pii if {
	access.masking_strategy == "partial_mask" with input as masking_input("account_id", "pii")
		with data.data_mesh.domain["accounts"]["account-master"].column_strategy as {"account_id": "no_mask"}
}

test_unknown_column_is_masked_by_domain_default if {
	access.masking_strategy == "full_hash" with input as masking_input("not_a_column", "sensitive")
}

test_unknown_classification_is_masked if {
	access.masking_strategy == "full_hash" with input as masking_input("account_id", "something_new")
}

test_missing_classification_is_masked if {
	access.masking_strategy == "full_hash" with input as {"column": "account_id", "product": account_master}
}

test_unknown_domain_strategy_is_masked if {
	access.masking_strategy == "full_hash" with input as masking_input("account_id", "sensitive")
		with data.data_mesh.domain["accounts"]["account-master"].column_strategy as {"account_id": "show_everything"}
}

test_domain_can_mask_more_than_floor if {
	access.masking_strategy == "full_mask" with input as masking_input("account_id", "pii")
		with data.data_mesh.domain["accounts"]["account-master"].column_strategy as {"account_id": "full_mask"}
}
