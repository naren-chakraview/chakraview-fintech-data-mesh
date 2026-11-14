"""Development producer step.

1. Create one Ed25519 key per producer workload (platform/lineage/keys/, gitignored), if missing.
2. Write the trust configuration (platform/lineage/trust/): product -> expected producer and its public key.
3. Sign each fixture snapshot's statement with its own producer's key into platform/lineage/attestations/.

Production: the trust configuration is reviewed platform config, and signing is KMS or Sigstore keyless.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "platform"))
sys.path.insert(0, str(REPO_ROOT))

from lineage.attest import generate_signing_key, publish_attestation  # noqa: E402
from lineage.producers import PRODUCERS  # noqa: E402

FIXTURES = REPO_ROOT / "platform/boundary/fixtures"
KEYS = REPO_ROOT / "platform/lineage/keys"
ATTESTATIONS = REPO_ROOT / "platform/lineage/attestations"
TRUST = REPO_ROOT / "platform/lineage/trust"


def ensure_producer_keys() -> None:
    KEYS.mkdir(parents=True, exist_ok=True)
    for key_name, _ in set(PRODUCERS.values()):
        if (KEYS / f"{key_name}.key").exists():
            continue
        private_pem, public_pem = generate_signing_key()
        (KEYS / f"{key_name}.key").write_bytes(private_pem)
        (KEYS / f"{key_name}.pub").write_bytes(public_pem)
        print(f"created producer key {key_name}")


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_trust() -> None:
    TRUST.mkdir(parents=True, exist_ok=True)
    products = {}
    for product_id, (key_name, spiffe_id) in PRODUCERS.items():
        shutil.copy(KEYS / f"{key_name}.pub", TRUST / f"{key_name}.pub")
        products[product_id] = {"producer": spiffe_id, "public_key": f"{key_name}.pub"}
    (TRUST / "producers.json").write_text(json.dumps({"products": products}, indent=2, sort_keys=True) + "\n")


def main() -> None:
    ensure_producer_keys()
    write_trust()
    ATTESTATIONS.mkdir(parents=True, exist_ok=True)
    for product_id, (key_name, spiffe_id) in PRODUCERS.items():
        snapshot = (FIXTURES / f"{product_id}.json").read_bytes()
        target = publish_attestation(
            product_id, snapshot,
            private_key_pem=(KEYS / f"{key_name}.key").read_bytes(), keyid=key_name,
            producer_spiffe_id=spiffe_id, code_commit=_commit(),
            input_snapshots=[], out_dir=ATTESTATIONS,
        )
        print(f"attested {product_id} as {key_name} -> {target}")


if __name__ == "__main__":
    main()
