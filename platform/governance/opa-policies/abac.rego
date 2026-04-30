package data_mesh.access

# Default deny
default allow = false

# Auto-approve: read-only, non-sensitive, internal user
allow {
    input.action == "read"
    input.user_role in ["internal-analyst", "fraud-team"]
    input.data_sensitivity in ["public", "public"]
    not input.requires_approval
}

# Domain owner approval required: write or sensitive data
requires_approval {
    input.action == "write"
}

requires_approval {
    input.data_sensitivity in ["pii", "confidential"]
}

# PII column masking required for external users
mask_pii {
    input.user_role in ["external-analyst"]
    input.target_columns[_] == "account_id"
}

mask_pii {
    input.user_role in ["external-analyst"]
    input.target_columns[_] == "account_holder_name"
}
