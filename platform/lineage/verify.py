"""Verifier side: check the DSSE signature and that the subject digest matches the served snapshot."""

import base64
import binascii
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .attest import PAYLOAD_TYPE, PREDICATE_TYPE, pae, snapshot_digest


class LineageError(Exception):
    """The attestation is missing, malformed, badly signed, or does not describe this snapshot."""


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise LineageError("producer key is not Ed25519")
    return key


def verify_envelope(envelope: dict, public_key: Ed25519PublicKey) -> dict:
    """Return the statement if the signature verifies. Raises LineageError otherwise."""
    try:
        if envelope["payloadType"] != PAYLOAD_TYPE:
            raise LineageError("unexpected payload type")
        payload = base64.b64decode(envelope["payload"], validate=True)
        signatures = envelope["signatures"]
        if not signatures:
            raise LineageError("no signatures")
        signature = base64.b64decode(signatures[0]["sig"], validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error) as exc:
        raise LineageError("envelope is malformed") from exc

    try:
        public_key.verify(signature, pae(PAYLOAD_TYPE, payload))
    except InvalidSignature as exc:
        raise LineageError("signature does not verify") from exc

    try:
        statement = json.loads(payload)
    except ValueError as exc:
        raise LineageError("payload is not JSON") from exc
    if statement.get("predicateType") != PREDICATE_TYPE:
        raise LineageError("unexpected predicate type")
    return statement


def verify_snapshot(envelope: dict, public_key: Ed25519PublicKey, snapshot: bytes, product_id: str) -> bool:
    """True only if the signature verifies and the subject digest is the SHA-256 of this snapshot."""
    try:
        statement = verify_envelope(envelope, public_key)
    except LineageError:
        return False
    subjects = statement.get("subject", [])
    if len(subjects) != 1 or subjects[0].get("name") != product_id:
        return False
    return subjects[0].get("digest", {}).get("sha256") == snapshot_digest(snapshot)
