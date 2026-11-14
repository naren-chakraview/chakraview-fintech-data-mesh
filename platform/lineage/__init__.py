"""Lineage as attestation: signed in-toto statements (DSSE envelopes) for published snapshots.

Import as `lineage` with platform/ on sys.path (the stdlib `platform` module shadows this directory).
"""

from .attest import (
    PREDICATE_TYPE,
    build_statement,
    generate_signing_key,
    publish_attestation,
    sign_envelope,
    snapshot_digest,
)
from .verify import LineageError, load_public_key, verify_envelope, verify_snapshot

__all__ = [
    "PREDICATE_TYPE",
    "LineageError",
    "build_statement",
    "generate_signing_key",
    "load_public_key",
    "publish_attestation",
    "sign_envelope",
    "snapshot_digest",
    "verify_envelope",
    "verify_snapshot",
]
