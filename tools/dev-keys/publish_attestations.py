"""Producer step: sign each fixture snapshot's lineage statement into platform/lineage/attestations/.

Run after make_signing_key.py. The statement names the producer workload, the code commit, and the
snapshot digest. Verification is in platform/lineage/verify.py.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "platform"))
sys.path.insert(0, str(REPO_ROOT))

from lineage.attest import publish_attestation  # noqa: E402

FIXTURES = REPO_ROOT / "platform/boundary/fixtures"
KEYS = REPO_ROOT / "platform/lineage/keys"
OUT = REPO_ROOT / "platform/lineage/attestations"

PRODUCERS = {
    "risk-compliance.risk-scores": "spiffe://chakracommerce.com/ns/risk/sa/producer",
    "accounts.account-master": "spiffe://chakracommerce.com/ns/batch/sa/nightly",
}


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy(KEYS / "producer.pub", OUT / "producer.pub")
    private_pem = (KEYS / "producer.key").read_bytes()
    for product_id, producer in PRODUCERS.items():
        snapshot = (FIXTURES / f"{product_id}.json").read_bytes()
        target = publish_attestation(
            product_id, snapshot,
            private_key_pem=private_pem, keyid="producer-dev",
            producer_spiffe_id=producer, code_commit=_commit(),
            input_snapshots=[], out_dir=OUT,
        )
        print(f"attested {product_id} -> {target}")


if __name__ == "__main__":
    main()
