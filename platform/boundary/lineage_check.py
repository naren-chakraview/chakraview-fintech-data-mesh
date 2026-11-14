"""lineage_verified for a read: the producer's attestation must verify and describe these exact bytes."""

import json
from pathlib import Path
from typing import Callable

from lineage.verify import load_public_key, verify_snapshot


def make_lineage_check(lineage_dir: Path) -> Callable[[str, bytes], bool]:
    lineage_dir = Path(lineage_dir)

    def check(product_id: str, snapshot: bytes) -> bool:
        try:
            envelope = json.loads((lineage_dir / f"{product_id}.dsse.json").read_text())
            public_key = load_public_key(lineage_dir / "producer.pub")
        except (OSError, ValueError):
            return False
        return verify_snapshot(envelope, public_key, snapshot, product_id)

    return check
