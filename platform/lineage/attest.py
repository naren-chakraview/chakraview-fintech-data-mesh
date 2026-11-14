"""Producer side: build an in-toto Statement v1, sign it as a DSSE envelope with Ed25519.

Dev keys come from tools/dev-keys/make_signing_key.py and are never committed. Production
uses KMS or Sigstore.
"""

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://chakracommerce.com/data-provenance/v1"
PAYLOAD_TYPE = "application/vnd.in-toto+json"


def snapshot_digest(snapshot: bytes) -> str:
    return hashlib.sha256(snapshot).hexdigest()


def build_statement(
    product_id: str,
    snapshot: bytes,
    producer_spiffe_id: str,
    code_commit: str,
    input_snapshots: List[dict],
    run_time: Optional[datetime] = None,
) -> dict:
    """Subject is the product and the SHA-256 of the published snapshot bytes."""
    return {
        "_type": STATEMENT_TYPE,
        "subject": [{"name": product_id, "digest": {"sha256": snapshot_digest(snapshot)}}],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "producer": producer_spiffe_id,
            "code_commit": code_commit,
            "inputs": input_snapshots,
            "run_time": (run_time or datetime.now(timezone.utc)).isoformat(),
        },
    }


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE pre-authentication encoding."""
    type_bytes = payload_type.encode()
    return b"DSSEv1 %d %b %d %b" % (len(type_bytes), type_bytes, len(payload), payload)


def sign_envelope(statement: dict, private_key: Ed25519PrivateKey, keyid: str) -> dict:
    payload = json.dumps(statement, sort_keys=True, separators=(",", ":")).encode()
    signature = private_key.sign(pae(PAYLOAD_TYPE, payload))
    return {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode(),
        "signatures": [{"keyid": keyid, "sig": base64.b64encode(signature).decode()}],
    }


def generate_signing_key() -> tuple:
    """Return (private key PEM, public key PEM) for an Ed25519 producer key."""
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem, public_pem


def publish_attestation(
    product_id: str,
    snapshot: bytes,
    *,
    private_key_pem: bytes,
    keyid: str,
    producer_spiffe_id: str,
    code_commit: str,
    input_snapshots: List[dict],
    out_dir: Path,
) -> Path:
    """Sign the snapshot's statement and write <out_dir>/<product_id>.dsse.json."""
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    statement = build_statement(
        product_id, snapshot, producer_spiffe_id, code_commit, input_snapshots
    )
    envelope = sign_envelope(statement, private_key, keyid)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{product_id}.dsse.json"
    target.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return target
