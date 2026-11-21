"""Which workload produces which product, and the key name for that workload.

This is the development mapping used by tools/dev-keys/. Production states the same mapping in the trust
configuration that the boundary reads, which is written and reviewed by the platform team, never by a producer.
"""

# The products the boundary writes (direct writes, and accepted proposals) are produced by the governed writer: the
# boundary is the producer of record, and each statement names the service or the agent that wrote it (written_by).
WRITER = ("governed-writer", "spiffe://chakracommerce.com/ns/boundary/sa/governed-writer")

PRODUCERS = {
    "risk-compliance.risk-scores": WRITER,
    "accounts.customer-intake": WRITER,
    "risk-compliance.score-freshness-summary": WRITER,
    "accounts.account-master": ("nightly-batch", "spiffe://chakracommerce.com/ns/batch/sa/nightly"),
    # The governed write path. Only accepted proposals reach this product, so the boundary is its producer of record.
    "risk-compliance.risk-review-notes": ("governed-writer", "spiffe://chakracommerce.com/ns/boundary/sa/governed-writer"),
}
