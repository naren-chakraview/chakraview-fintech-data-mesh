"""Create the dev workload CA and issue client certificates for the named test workloads.

Writes tools/dev-ca/out/ (gitignored): ca.pem, ca.key, gateway.pem / gateway.key (TLS server
certificate), and <name>.pem / <name>.key for each workload with its SPIFFE ID in the URI SAN. Development only. Production uses SPIRE.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402

from shared.identity.devtools import issue_server_cert, issue_workload_cert, make_ca  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"

WORKLOADS = {
    "notebook": "spiffe://chakracommerce.com/ns/analytics/sa/notebook",
    "nightly-batch": "spiffe://chakracommerce.com/ns/batch/sa/nightly",
    "risk-producer": "spiffe://chakracommerce.com/ns/risk/sa/producer",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ca_key, ca_cert = make_ca()
    (OUT / "ca.pem").write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    (OUT / "ca.key").write_bytes(ca_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    gateway_key, gateway_cert = issue_server_cert(ca_key, ca_cert, ["localhost", "gateway"])
    (OUT / "gateway.key").write_bytes(gateway_key)
    (OUT / "gateway.pem").write_bytes(gateway_cert)
    for name, spiffe_id in WORKLOADS.items():
        key_pem, cert_pem = issue_workload_cert(ca_key, ca_cert, spiffe_id)
        (OUT / f"{name}.key").write_bytes(key_pem)
        (OUT / f"{name}.pem").write_bytes(cert_pem)
        print(f"issued {name}: {spiffe_id}")


if __name__ == "__main__":
    main()
