# Platform guardrails. Owned by the platform team (see CODEOWNERS).
#
# Every decision is platform_allow AND the owning domain's allow (abac.rego). A domain
# policy can add restrictions, never remove these. Input shape (set by platform/boundary):
#   input.principal.subject        verified JWT subject ("" or missing is denied)
#   input.principal.roles          verified role claims (for a delegated call: the person's roles)
#   input.principal.owns           verified domain ownership claims (owner actions only)
#   input.workload.spiffe_id       verified SPIFFE ID of the workload (for a delegated call: the agent)
#   input.action                   "read" | "aggregate" | "request_access" | "write" | "propose" | "accept" | "reject" | "rollback"
#   input.write                    for a write: {kind, classification, caller, producer, subject_or_grant}
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

owner_action if input.action in {"accept", "reject", "rollback", "accept_consent"}

# Subject consent (W7): the person a personal value describes is the only one who may accept it. The boundary sets
# consent.subject_match from her IdP-attested identity; an agent (any delegation) and the domain owner never match.
default platform_consent_allow := false

platform_consent_allow if {
	input.action == "accept_consent"
	input.principal.subject != ""
	startswith(input.workload.spiffe_id, "spiffe://")
	not input.delegation
	input.consent.subject_match == true
}

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

masking_floor := "no_mask" if input.column_classification in {"public", "internal"}

# --- Write tiers (addendum W2). Who decided the data decides whether a human gate applies. ---
#
# A captured write records facts a person or system of record supplied, so no human gate applies: the customer
# decided the values. A derived write records what a writer computed or judged from data it read. A service's
# derived output was reviewed once, at code review. An agent decides per request, so for confidential output the
# review moves to the write: an owner accepts it. An agent never creates personal data.
#
# The outcome is the platform's; a domain may only make it stricter (abac.rego).

default platform_write_allow := false

platform_write_allow if {
	input.action == "write"
	input.principal.subject != ""
	startswith(input.workload.spiffe_id, "spiffe://")
	delegation_ok
}

default write_platform := "forbidden"

# Captured: a service records what it was given; an agent only for its own data subject (or an intake grant).
write_platform := "direct" if {
	input.write.kind == "captured"
	input.write.caller == "service"
}

write_platform := "direct" if {
	input.write.kind == "captured"
	input.write.caller == "agent"
	input.write.subject_or_grant == true
}

# Derived, public or internal: anyone may write it directly.
write_platform := "direct" if {
	input.write.kind == "derived"
	input.write.classification in {"public", "internal"}
}

# Derived, confidential or sensitive: a listed producer writes directly; an agent proposes and an owner accepts.
write_platform := "direct" if {
	input.write.kind == "derived"
	input.write.classification in {"confidential", "sensitive"}
	input.write.caller == "service"
	input.write.producer == true
}

write_platform := "requires_owner_review" if {
	input.write.kind == "derived"
	input.write.classification in {"confidential", "sensitive"}
	input.write.caller == "agent"
}

# Derived, personal or restricted: a listed producer only. An agent is refused: agents do not create personal data.
write_platform := "direct" if {
	input.write.kind == "derived"
	input.write.classification in {"pii", "restricted"}
	input.write.caller == "service"
	input.write.producer == true
}

# Addendum 2 (W7): an agent's personal derived value that describes exactly one data subject, on a product whose
# contract opts in, is blessed by that subject, not refused. Only the subject can accept it.
subject_consent_possible if {
	input.write.single_subject == true
	input.write.subject_consent == true
}

write_platform := "requires_subject_consent" if {
	input.write.kind == "derived"
	input.write.classification in {"pii", "restricted"}
	input.write.caller == "agent"
	subject_consent_possible
}

# Several subjects, or no identifiable subject: no single person could bless it, so it is refused.
write_platform := "refused_pii" if {
	input.write.kind == "derived"
	input.write.classification in {"pii", "restricted"}
	input.write.caller == "agent"
	not subject_consent_possible
}
