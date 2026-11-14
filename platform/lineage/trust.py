"""The lineage trust configuration: which producer is expected for each product, and that producer's key.

The trust directory is separate from the attestation directory, and the boundary mounts it read-only. Whoever
can write an attestation cannot change which key verifies it or which producer is expected.
Layout:
    <trust_dir>/producers.json   {"products": {"<product>": {"producer": "<spiffe>", "public_key": "<file>"}}}
    <trust_dir>/<file>           Ed25519 public key (PEM)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .attest import snapshot_digest
from .verify import LineageError, load_public_key, verify_envelope


@dataclass(frozen=True)
class ProducerTrust:
    product_id: str
    producer_spiffe_id: str
    public_key: Ed25519PublicKey


def load_trust(trust_dir: Path) -> Dict[str, ProducerTrust]:
    trust_dir = Path(trust_dir)
    document = json.loads((trust_dir / "producers.json").read_text())
    trust = {}
    for product_id, entry in document["products"].items():
        trust[product_id] = ProducerTrust(
            product_id=product_id,
            producer_spiffe_id=entry["producer"],
            public_key=load_public_key(trust_dir / entry["public_key"]),
        )
    return trust


def verify_product(product_id: str, snapshot: bytes, attestation_dir: Path,
                   trust: Dict[str, ProducerTrust]) -> bool:
    """True only if: the product has a trust entry, the attestation verifies under that entry's key,
    the statement names the expected producer, and its subject is this exact snapshot."""
    expected: Optional[ProducerTrust] = trust.get(product_id)
    if expected is None:
        return False
    try:
        envelope = json.loads((Path(attestation_dir) / f"{product_id}.dsse.json").read_text())
        statement = verify_envelope(envelope, expected.public_key)
    except (OSError, ValueError, LineageError):
        return False
    if statement.get("predicate", {}).get("producer") != expected.producer_spiffe_id:
        return False
    subjects = statement.get("subject", [])
    if len(subjects) != 1 or subjects[0].get("name") != product_id:
        return False
    return subjects[0].get("digest", {}).get("sha256") == snapshot_digest(snapshot)
