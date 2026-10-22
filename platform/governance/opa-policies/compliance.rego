package data_mesh.compliance

import rego.v1

# Retention enforcement
enforce_retention contains violation if {
	input.table_retention_days < 365
	violation := {
		"message": "Retention policy less than 1 year violates fintech standards",
		"table": input.table,
		"retention_days": input.table_retention_days,
	}
}

# Masking enforcement: every PII column must be masked.
enforce_masking contains violation if {
	input.column_classification == "pii"
	not input.is_masked
	violation := {
		"message": "PII column must be masked",
		"column": input.column,
		"table": input.table,
	}
}

# Audit logging requirement
audit_required if true
