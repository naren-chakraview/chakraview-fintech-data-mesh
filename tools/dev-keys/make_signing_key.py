"""Create the dev Ed25519 producer keys (one per producer workload), gitignored.

Production uses KMS or Sigstore. `publish_attestations.py` does the same and also writes the trust config.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_attestations import ensure_producer_keys  # noqa: E402


if __name__ == "__main__":
    ensure_producer_keys()
