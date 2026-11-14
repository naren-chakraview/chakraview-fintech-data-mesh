package data_mesh.guardrails_test

import rego.v1

import data.data_mesh.guardrails

person := {"subject": "a@chakra.fintech", "roles": ["analyst"]}

test_verified_person_and_workload_pass_platform if {
	guardrails.platform_allow with input as {"action": "read", "principal": person, "workload": {"spiffe_id": "spiffe://chakracommerce.com/ns/batch/sa/nightly"}}
}

test_empty_subject_fails_platform if {
	not guardrails.platform_allow with input as {"action": "read", "principal": {"subject": "", "roles": []}, "workload": {"spiffe_id": "spiffe://x/y"}}
}

test_missing_principal_fails_platform if {
	not guardrails.platform_allow with input as {"action": "read", "workload": {"spiffe_id": "spiffe://x/y"}}
}

test_write_fails_platform if {
	not guardrails.platform_allow with input as {"action": "write", "principal": person, "workload": {"spiffe_id": "spiffe://x/y"}}
}

test_pii_product_always_requires_approval if {
	guardrails.platform_requires_approval with input as {"product": {"classification": "pii"}}
}

test_public_product_does_not_require_platform_approval if {
	not guardrails.platform_requires_approval with input as {"product": {"classification": "public"}}
}

test_masking_floor_pii_is_partial if {
	guardrails.masking_floor == "partial_mask" with input as {"column_classification": "pii"}
}

test_masking_floor_unknown_is_full_hash if {
	guardrails.masking_floor == "full_hash" with input as {"column_classification": "PII"}
}

test_masking_floor_sensitive_is_partial if {
	guardrails.masking_floor == "partial_mask" with input as {"column_classification": "sensitive"}
}

test_masking_floor_public_is_no_mask if {
	guardrails.masking_floor == "no_mask" with input as {"column_classification": "public"}
}

test_provenance_required_and_unverified_read_fails_platform if {
	not guardrails.platform_allow with input as {"action": "read", "principal": person, "workload": {"spiffe_id": "spiffe://x/y"}, "product": {"require_provenance": true}, "lineage_verified": false}
}

test_provenance_required_and_missing_lineage_fails_platform if {
	not guardrails.platform_allow with input as {"action": "read", "principal": person, "workload": {"spiffe_id": "spiffe://x/y"}, "product": {"require_provenance": true}}
}

test_provenance_required_and_verified_read_passes_platform if {
	guardrails.platform_allow with input as {"action": "read", "principal": person, "workload": {"spiffe_id": "spiffe://x/y"}, "product": {"require_provenance": true}, "lineage_verified": true}
}

test_product_without_provenance_requirement_ignores_lineage if {
	guardrails.platform_allow with input as {"action": "read", "principal": person, "workload": {"spiffe_id": "spiffe://x/y"}, "product": {"require_provenance": false}, "lineage_verified": false}
}

test_access_request_is_not_gated_by_provenance if {
	guardrails.platform_allow with input as {"action": "request_access", "principal": person, "workload": {"spiffe_id": "spiffe://x/y"}, "product": {"require_provenance": true}}
}
