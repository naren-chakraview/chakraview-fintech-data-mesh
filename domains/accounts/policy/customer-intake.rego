# Domain policy for accounts/customer-intake. Owned by the accounts domain (see CODEOWNERS).
# The platform guardrails still apply. Personal data is masked on read for everyone except a KYC grant (purpose kyc),
# and a customer writes only their own record: the boundary checks that the record's customer_iri is the one minted
# from the writing person's identity (addendum W3).
package data_mesh.domain["accounts"]["customer-intake"]

import rego.v1

default allow := false

# Reads: KYC officers see the intake, masked at the platform floor for personal data.
allow if {
	input.action in {"read", "request_access"}
	input.principal.roles[_] in {"kyc_officer"}
}

# Writes: a customer writes their own intake. The record must be theirs; the boundary checks that, not this file.
default allow_write := false

allow_write if {
	input.action == "write"
	input.principal.roles[_] in {"customer", "intake_service"}
}

allow_agents := ["spiffe://chakracommerce.com/ns/agents/sa/onboarding-agent"]

agent_write_columns := ["customer_iri", "legal_name", "ssn", "address"]

requires_approval if input.product.approval_required == true

column_strategy := {
	"customer_iri": "no_mask",
	"legal_name": "full_mask",
	"ssn": "full_mask",
	"address": "full_mask",
}

# A KYC read sees the last digits of personal values, never more.
kyc_column_strategy := {
	"ssn": "partial_mask",
	"address": "partial_mask",
	"legal_name": "partial_mask",
}

# Accept, reject and roll back: the domain owner, for a product the owner owns (addendum W2: the owner can roll back any
# write, and a rollback is signed and audited).
default allow_owner_actions := false

allow_owner_actions if {
	input.principal.roles[_] == "data_owner"
	input.product.owner == input.principal.owns[_]
}
