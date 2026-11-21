"""Create the dev certificate authorities and the certificates each service mounts.

Two CAs, so that trust is scoped:
- dev CA: issues workload certificates (SPIFFE URI SANs) and the gateway's edge TLS certificate. Clients use it.
- internal CA: issues the services' TLS certificates and the gateway's client certificate. Only the gateway holds
  a certificate from it, so a workload certificate cannot reach the boundary or discovery directly.

Writes tools/dev-ca/out/ (gitignored). The CA private keys stay in out/ca/ and out/internal/, which no service mounts.
Each service mounts only its own directory under out/services/. Development only. Production uses SPIRE.
"""

import shutil
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
    # The risk-review agent's client certificate. Its sidecar binds delegated tokens to it.
    "risk-review-agent": "spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent",
}
GATEWAY_SPIFFE = "spiffe://chakracommerce.com/ns/edge/sa/gateway"


def _pem_key(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _pem_cert(cert) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    dev_key, dev_cert = make_ca("chakra dev workload CA")
    internal_key, internal_cert = make_ca("chakra dev internal service CA")

    _write(OUT / "ca" / "ca.key", _pem_key(dev_key))
    _write(OUT / "ca" / "ca.pem", _pem_cert(dev_cert))
    _write(OUT / "internal" / "ca.key", _pem_key(internal_key))
    _write(OUT / "internal" / "ca.pem", _pem_cert(internal_cert))

    for name, spiffe_id in WORKLOADS.items():
        key_pem, cert_pem = issue_workload_cert(dev_key, dev_cert, spiffe_id)
        _write(OUT / f"{name}.key", key_pem)
        _write(OUT / f"{name}.pem", cert_pem)
        print(f"issued workload {name}: {spiffe_id}")

    # Gateway: the edge certificate clients trust (dev CA), and the client certificate it presents to services.
    edge_key, edge_cert = issue_server_cert(dev_key, dev_cert, ["localhost", "gateway"])
    client_key, client_cert = issue_workload_cert(internal_key, internal_cert, GATEWAY_SPIFFE)
    gateway = OUT / "services" / "gateway"
    _write(gateway / "edge.key", edge_key)
    _write(gateway / "edge.pem", edge_cert)
    _write(gateway / "client.key", client_key)
    _write(gateway / "client.pem", client_cert)
    _write(gateway / "ca.pem", _pem_cert(dev_cert))
    _write(gateway / "internal-ca.pem", _pem_cert(internal_cert))

    # The delegation sidecars (zt-gateway, one per delegating workload). Each serves TLS with a dev CA certificate
    # that clients on the same network trust. Development only.
    for sidecar, names in (("agent-zt", ["localhost", "agent-zt"]), ("boundary-zt", ["boundary", "localhost"])):
        key, cert = issue_server_cert(dev_key, dev_cert, names)
        target = OUT / "services" / sidecar
        _write(target / "server.key", key)
        _write(target / "server.pem", cert)
        _write(target / "ca.pem", _pem_cert(dev_cert))
        print(f"issued {sidecar} server certificate (dev CA)")

    for service in ("boundary", "discovery"):
        key, cert = issue_server_cert(internal_key, internal_cert, [service])
        target = OUT / "services" / service
        _write(target / "server.key", key)
        _write(target / "server.pem", cert)
        _write(target / "ca.pem", _pem_cert(internal_cert))
        print(f"issued {service} server certificate (internal CA)")


if __name__ == "__main__":
    main()
