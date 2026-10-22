package data_mesh.compliance_test

import rego.v1

import data.data_mesh.compliance

test_retention_under_one_year_violates if {
	count(compliance.enforce_retention) == 1 with input as {"table": "t", "table_retention_days": 180}
}

test_retention_one_year_passes if {
	count(compliance.enforce_retention) == 0 with input as {"table": "t", "table_retention_days": 365}
}

test_unmasked_pii_column_violates if {
	count(compliance.enforce_masking) == 1 with input as {"table": "t", "column": "account_id", "column_classification": "pii", "is_masked": false}
}

test_masked_pii_column_passes if {
	count(compliance.enforce_masking) == 0 with input as {"table": "t", "column": "account_id", "column_classification": "pii", "is_masked": true}
}

test_unmasked_public_column_passes if {
	count(compliance.enforce_masking) == 0 with input as {"table": "t", "column": "merchant_id", "column_classification": "public", "is_masked": false}
}
