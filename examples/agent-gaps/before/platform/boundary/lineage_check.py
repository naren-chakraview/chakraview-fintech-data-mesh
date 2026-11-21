"""lineage_verified for a read: the attestation must verify under the trust configuration and describe these bytes."""

from pathlib import Path
from typing import Callable

from lineage.trust import load_trust, verify_product


def make_lineage_check(attestation_dir: Path, trust_dir: Path) -> Callable[[str, bytes], bool]:
    attestation_dir = Path(attestation_dir)
    trust_dir = Path(trust_dir)

    def check(product_id: str, snapshot: bytes) -> bool:
        try:
            trust = load_trust(trust_dir)
        except (OSError, ValueError, KeyError):
            return False
        return verify_product(product_id, snapshot, attestation_dir, trust)

    return check
