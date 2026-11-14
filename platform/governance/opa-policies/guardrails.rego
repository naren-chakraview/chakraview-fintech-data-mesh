# Platform guardrails. Owned by the platform team (see CODEOWNERS).
#
# Every decision is platform_allow AND the owning domain's allow (abac.rego). A domain
# policy can add restrictions, never remove these. Input shape (set by platform/boundary):
#   input.principal.subject        verified JWT subject ("" or missing is denied)
#   input.principal.roles          verified role claims
#   input.workload.spiffe_id       verified SPIFFE ID from the client certificate
#   input.action                   "read" | "request_access" | "write"
#   input.product.classification   highest column classification of the product
#   input.column_classification    classification of one column (masking only)
#   input.product.require_provenance  the product's contract: reads need verified lineage
#   input.lineage_verified         whether the snapshot's attestation verified (reads only)
package data_mesh.guardrails

import rego.v1

# Deny without a verified person and a verified workload. The read path never writes.
default platform_allow := false

platform_allow if {
	input.principal.subject != ""
	startswith(input.workload.spiffe_id, "spiffe://")
	input.action in {"read", "request_access"}
	provenance_ok
}

# A product that requires provenance is readable only when the snapshot's lineage verified. A SPARQL read
# has no single snapshot, so it carries no lineage_verified and is refused for such a product (fail closed).
# Access requests are not reads of data, so they are not gated by provenance.
provenance_ok if not input.product.require_provenance

provenance_ok if input.lineage_verified == true

provenance_ok if input.action == "request_access"

# Products with personal, confidential or restricted data always need approval, and a
# domain cannot switch that off.
default platform_requires_approval := false

platform_requires_approval if input.product.classification in {"pii", "confidential", "restricted"}

# Masking floor per column. Personal and sensitive data is never shown in the clear, and an
# unknown classification is masked (fail closed). A domain can only mask more than this floor.
default masking_floor := "full_hash"

masking_floor := "partial_mask" if input.column_classification in {"pii", "sensitive"}

masking_floor := "no_mask" if input.column_classification == "public"
