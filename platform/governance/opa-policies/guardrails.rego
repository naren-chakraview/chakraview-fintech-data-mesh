# Platform guardrails. Owned by the platform team (see CODEOWNERS).
#
# Every decision is platform_allow AND the owning domain's allow (abac.rego). A domain
# policy can add restrictions, never remove these. Input shape (set by platform/boundary):
#   input.principal.subject        verified JWT subject ("" or missing is denied)
#   input.principal.roles          verified role claims (for a delegated call: the person's roles)
#   input.principal.owns           verified domain ownership claims (owner actions only)
#   input.workload.spiffe_id       verified SPIFFE ID of the workload (for a delegated call: the agent)
#   input.action                   "read" | "aggregate" | "request_access" | "propose" | "accept" | "reject" | "rollback"
#   input.delegation               present only for a delegated call: {actor, chain}, verified from a gateway token
#   input.product.classification   highest column classification of the product
#   input.column_classification    classification of one column (masking only)
#   input.product.require_provenance  the product's contract: reads need verified lineage
#   input.lineage_verified         whether the snapshot's attestation verified (reads only)
package data_mesh.guardrails

import rego.v1

# A delegation chain names the current actor first and at most this many workloads in total.
max_delegation_depth := 2

delegation_ok if not input.delegation

delegation_ok if {
	input.delegation
	startswith(input.delegation.actor, "spiffe://")
	count(input.delegation.chain) <= max_delegation_depth
}

# Deny without a verified person and a verified workload. The read path never writes.
default platform_allow := false

platform_allow if {
	input.principal.subject != ""
	startswith(input.workload.spiffe_id, "spiffe://")
	input.action in {"read", "aggregate", "request_access"}
	provenance_ok
	delegation_ok
}

# A product that requires provenance is readable only when the snapshot's lineage verified. A SPARQL read
# has no single snapshot, so it carries no lineage_verified and is refused for such a product (fail closed).
# Access requests are not reads of data, so they are not gated by provenance.
provenance_ok if not input.product.require_provenance

provenance_ok if input.lineage_verified == true

provenance_ok if input.action == "request_access"

# Proposals are writes into a governed product, so only a delegated caller may make one: a person's own
# token cannot propose. Writing is never a side effect of a read.
default platform_propose_allow := false

platform_propose_allow if {
	input.action == "propose"
	input.principal.subject != ""
	startswith(input.workload.spiffe_id, "spiffe://")
	input.delegation
	delegation_ok
}

# Owner actions (accept, reject, roll back) need the owner's own token with no delegation. An agent can never
# accept a proposal, including its own: a delegated call fails this rule whatever the domain says.
default platform_owner_allow := false

platform_owner_allow if {
	input.action in {"accept", "reject", "rollback"}
	input.principal.subject != ""
	startswith(input.workload.spiffe_id, "spiffe://")
	not input.delegation
}

owner_action if input.action in {"accept", "reject", "rollback"}

# Products with personal, confidential or restricted data always need approval, and a
# domain cannot switch that off. Owner actions are not reads, so they need no grant.
default platform_requires_approval := false

platform_requires_approval if {
	input.product.classification in {"pii", "confidential", "restricted"}
	not owner_action
}

# A delegated read of personal data is never shown in the clear, whatever the domain says. A person's own
# read keeps the floor below.
delegated_personal if {
	input.delegation
	input.column_classification == "pii"
}

# Masking floor per column. Personal and sensitive data is never shown in the clear, and an
# unknown classification is masked (fail closed). A domain can only mask more than this floor.
default masking_floor := "full_hash"

masking_floor := "full_hash" if delegated_personal

masking_floor := "partial_mask" if {
	input.column_classification in {"pii", "sensitive"}
	not delegated_personal
}

masking_floor := "no_mask" if input.column_classification == "public"
