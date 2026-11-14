package data_mesh.access

import rego.v1

# Default deny: nothing is readable unless a rule below allows it.
default allow := false

default requires_approval := false

# Read access without approval: non-restricted data, internal analyst roles.
allow if {
	input.action == "read"
	input.user_role in {"analyst", "risk_analyst"}
	input.data_classification in {"public", "sensitive"}
}

# Restricted or PII data, and every write, needs the owning domain's approval.
requires_approval if input.action == "write"

requires_approval if input.data_classification in {"pii", "confidential", "restricted"}

# Fraud analysts get sensitive data only with the owning domain's approval.
requires_approval if {
	input.user_role == "fraud_analyst"
	input.data_classification == "sensitive"
}

# Fail closed: every column is masked unless a rule explicitly says otherwise.
default masking_strategy := "full_hash"

masking_strategy := "no_mask" if input.column_classification == "public"

masking_strategy := "partial_mask" if {
	input.column_classification == "sensitive"
	input.user_role in {"analyst", "risk_analyst"}
}
