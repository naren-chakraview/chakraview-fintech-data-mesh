"""Governed writes. An agent proposes; a domain owner accepts, rejects or rolls back.

Nothing a delegated caller sends reaches an authoritative product. A proposal is validated, rate-limited,
checked against the reads its agent made through the boundary, and signed. Only an owner's acceptance writes
a new snapshot, and that snapshot's signed statement chains back to the proposal and the acceptance.
"""
