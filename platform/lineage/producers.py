"""Which workload produces which product, and the key name for that workload.

This is the development mapping used by tools/dev-keys/. Production states the same mapping in the trust
configuration that the boundary reads, which is written and reviewed by the platform team, never by a producer.
"""

PRODUCERS = {
    "risk-compliance.risk-scores": ("risk-producer", "spiffe://chakracommerce.com/ns/risk/sa/producer"),
    "accounts.account-master": ("nightly-batch", "spiffe://chakracommerce.com/ns/batch/sa/nightly"),
}
