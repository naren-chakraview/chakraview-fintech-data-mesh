"""Create the dev Ed25519 producer key for lineage attestations (gitignored). Production uses KMS or Sigstore."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "platform"))

from lineage.attest import generate_signing_key  # noqa: E402

OUT = REPO_ROOT / "platform/lineage/keys"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    private_pem, public_pem = generate_signing_key()
    (OUT / "producer.key").write_bytes(private_pem)
    (OUT / "producer.pub").write_bytes(public_pem)
    print(f"wrote {OUT / 'producer.key'} and {OUT / 'producer.pub'}")


if __name__ == "__main__":
    main()
