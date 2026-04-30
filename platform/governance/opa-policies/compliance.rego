package data_mesh.compliance

# Retention enforcement
enforce_retention[violation] {
    input.table_retention_days < 365
    violation := {
        "message": "Retention policy less than 1 year violates fintech standards",
        "table": input.table,
        "retention_days": input.table_retention_days,
    }
}

# Masking enforcement for PII columns
enforce_masking[violation] {
    input.column in ["account_id", "ssn", "account_holder_name"]
    not input.is_masked
    violation := {
        "message": "PII column must be masked",
        "column": input.column,
        "table": input.table,
    }
}

# Audit logging requirement
audit_required {
    true
}
