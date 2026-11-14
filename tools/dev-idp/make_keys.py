"""Create the dev IdP signing key and its JWKS in tools/dev-idp/keys/ (gitignored)."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.identity.devtools import generate_rsa_keypair  # noqa: E402

KEYS = Path(__file__).resolve().parent / "keys"


def main() -> None:
    KEYS.mkdir(parents=True, exist_ok=True)
    private_pem, jwk = generate_rsa_keypair()
    (KEYS / "idp-private.pem").write_bytes(private_pem)
    (KEYS / "jwks.json").write_text(json.dumps({"keys": [jwk]}, indent=2))
    print(f"wrote {KEYS / 'idp-private.pem'} and {KEYS / 'jwks.json'}")


if __name__ == "__main__":
    main()
