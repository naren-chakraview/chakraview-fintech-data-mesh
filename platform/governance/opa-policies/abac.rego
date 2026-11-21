# Decision point. Combines the platform guardrails with the owning domain's policy.
#
# The domain policy lives at domains/<domain>/policy/<product>.rego, in the package
# data_mesh.domain["<domain>"]["<product>"]. A product with no domain policy has no
# domain_policy, so every decision is false and every column is masked (fail closed).
#
# A delegated call (an agent acting for a person) is allowed only where all three hold:
#   the person's own access (the grant, checked by the boundary, and the domain's roles),
#   the agent's capability (the domain names the agent, and the columns it asks for), and
#   the product's policy (the platform guardrails). The intersection is what the agent gets.
package data_mesh.access

import rego.v1

domain_policy := data.data_mesh.domain[input.product.domain][input.product.name]

default allow := false

# Reads, by a person or by an agent acting for one. A read may ask only for the columns the domain lists for agents.
allow if {
	input.action == "read"
	data.data_mesh.guardrails.platform_allow
	domain_policy.allow
	agent_permitted
}

# Aggregates (counts per group), by a person, or by an agent for the columns the domain lists for aggregates. A
# group is a count, not a row, so an agent may be allowed counts that it may not read as rows.
allow if {
	input.action == "aggregate"
	data.data_mesh.guardrails.platform_allow
	domain_policy.allow
	agent_aggregate_permitted
}

agent_aggregate_permitted if not input.delegation

agent_aggregate_permitted if {
	input.delegation
	agent_opted_in
	every column in object.get(input, "columns", []) {
		column in object.get(domain_policy, "agent_aggregate_columns", [])
	}
}

# Proposals: only an agent proposes, and only where the domain opts that agent in.
allow if {
	data.data_mesh.guardrails.platform_propose_allow
	domain_policy.allow_propose
	agent_opted_in
}

# Writes (addendum W2): the person, the agent and the product must all allow the write. The grant is checked by
# the boundary (write needs a grant when the product requires approval), and the outcome by write_outcome below.
allow if {
	input.action == "write"
	data.data_mesh.guardrails.platform_write_allow
	domain_policy.allow_write
	agent_write_permitted
}

agent_write_permitted if not input.delegation

agent_write_permitted if {
	input.delegation
	agent_opted_in
	every column in object.get(input, "columns", []) {
		column in object.get(domain_policy, "agent_write_columns", [])
	}
}

# The outcome of a write: the platform's, or the domain's if the domain is stricter. A domain can only tighten it.
write_severity := {"direct": 0, "requires_owner_review": 1, "forbidden": 2, "refused_pii": 3}

write_outcome := data.data_mesh.guardrails.write_platform if {
	write_severity[data.data_mesh.guardrails.write_platform] >= write_severity[domain_write]
}

write_outcome := domain_write if {
	write_severity[domain_write] > write_severity[data.data_mesh.guardrails.write_platform]
}

domain_write := object.get(domain_policy, "write_outcome", "direct")

# Owner actions: the owner's own token, no delegation, and the domain grants owner actions.
allow if {
	data.data_mesh.guardrails.platform_owner_allow
	domain_policy.allow_owner_actions
}

agent_permitted if not input.delegation

agent_permitted if {
	input.delegation
	agent_opted_in
	agent_columns_ok
}

# An agent is refused unless the domain names it by SPIFFE ID, on every product. For a product with personal,
# confidential or restricted data this is the default the platform relies on, and the domain cannot widen it.
agent_opted_in if input.delegation.actor in object.get(domain_policy, "allow_agents", [])

# An agent may ask only for the columns the domain lists for agents. Anything else is refused, not silently
# dropped, so the caller can see what it was not allowed to read.
agent_columns_ok if {
	every column in object.get(input, "columns", []) {
		column in object.get(domain_policy, "agent_columns", [])
	}
}

default requires_approval := false

requires_approval if {
	not owner_action
	data.data_mesh.guardrails.platform_requires_approval
}

requires_approval if {
	not owner_action
	domain_policy.requires_approval
}

owner_action if input.action in {"accept", "reject", "rollback"}

# Masking strategies ordered from least to most strict. The stricter of the platform
# floor and the domain's strategy wins, so a domain cannot loosen the floor.
strictness := {
	"no_mask": 0,
	"partial_mask": 1,
	"hash_mask": 2,
	"full_hash": 3,
	"full_mask": 4,
}

# Unlisted columns are masked by the domain default. A domain shows a column only by listing it.
default domain_strategy := "full_hash"

# A KYC read (purpose "kyc") may use the domain's kyc_column_strategy for the columns it lists: the value is shown at
# the platform floor, never in the clear for a column the floor masks.
kyc_override if {
	input.purpose == "kyc"
	domain_policy.kyc_column_strategy[input.column]
}

domain_strategy := s if {
	kyc_override
	s := domain_policy.kyc_column_strategy[input.column]
}

domain_strategy := s if {
	not kyc_override
	s := domain_policy.column_strategy[input.column]
}

default masking_strategy := "full_hash"

masking_strategy := data.data_mesh.guardrails.masking_floor if {
	strictness[data.data_mesh.guardrails.masking_floor] >= strictness[domain_strategy]
}

masking_strategy := domain_strategy if {
	strictness[domain_strategy] > strictness[data.data_mesh.guardrails.masking_floor]
}
