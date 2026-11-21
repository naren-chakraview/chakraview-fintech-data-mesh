# Decision point. Combines the platform guardrails with the owning domain's policy.
#
# The domain policy lives at domains/<domain>/policy/<product>.rego, in the package
# data_mesh.domain["<domain>"]["<product>"]. A product with no domain policy has no
# domain_policy, so every decision is false and every column is masked (fail closed).
package data_mesh.access

import rego.v1

domain_policy := data.data_mesh.domain[input.product.domain][input.product.name]

default allow := false

allow if {
	data.data_mesh.guardrails.platform_allow
	domain_policy.allow
}

default requires_approval := false

requires_approval if data.data_mesh.guardrails.platform_requires_approval

requires_approval if domain_policy.requires_approval

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

domain_strategy := s if {
	s := domain_policy.column_strategy[input.column]
}

default masking_strategy := "full_hash"

masking_strategy := data.data_mesh.guardrails.masking_floor if {
	strictness[data.data_mesh.guardrails.masking_floor] >= strictness[domain_strategy]
}

masking_strategy := domain_strategy if {
	strictness[domain_strategy] > strictness[data.data_mesh.guardrails.masking_floor]
}
