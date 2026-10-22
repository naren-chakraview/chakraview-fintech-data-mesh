package data_mesh.access_test

import rego.v1

import data.data_mesh.access

test_unknown_classification_is_masked if {
	access.masking_strategy == "full_hash" with input as {"column_classification": "something_new", "user_role": "risk_analyst"}
}

test_missing_classification_is_masked if {
	access.masking_strategy == "full_hash" with input as {"user_role": "risk_analyst"}
}

test_public_column_is_not_masked if {
	access.masking_strategy == "no_mask" with input as {"column_classification": "public", "user_role": "external_analyst"}
}

test_pii_is_masked_even_for_internal_analysts if {
	access.masking_strategy == "full_hash" with input as {"column_classification": "pii", "user_role": "risk_analyst"}
}

test_external_analyst_cannot_read_by_default if {
	not access.allow with input as {"action": "read", "user_role": "external_analyst", "data_classification": "public"}
}

test_pii_requires_approval if {
	access.requires_approval with input as {"action": "read", "data_classification": "pii"}
}
