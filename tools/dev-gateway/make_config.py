"""Dev material for the delegation sidecars (zt-gateway) in docker-compose.

Two sidecars, each with its own signing key:
  agent-zt     shares the agent's network namespace. The agent's edge mint and token exchange happen on its admin
               listener, on loopback. It signs tokens for the agent.
  boundary-zt  shares the boundary's network namespace. It verifies the agent's tokens on its proxy listener and
               forwards the verified headers and token to the boundary's loopback listener.

Writes tools/dev-gateway/out/ (gitignored). Run after `make trust-keys`, which creates the dev CA and the IdP keys
this reads. Development only: static keys, bootstrap tokens and a dev IdP. Production uses SPIRE, KMS-held keys and
the company IdP.
"""

import json
import secrets
import shutil
import sys
from pathlib import Path

import jwt
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "out"
CA_OUT = REPO / "tools/dev-ca/out"
IDP_JWKS = REPO / "tools/dev-idp/keys/jwks.json"

TRUST_DOMAIN = "chakracommerce.com"
IDP_ISSUER = "http://dev-idp:8090"
AUDIENCE = "data-mesh"
AGENT = f"spiffe://{TRUST_DOMAIN}/ns/agents/sa/risk-review-agent"
BOUNDARY = f"spiffe://{TRUST_DOMAIN}/ns/boundary/sa/boundary"
ANALYSTS = ["risk.analyst@chakra.fintech"]

SIDECARS = {
    "agent-zt": {"kid": "agent-zt-1", "protected": AGENT},
    "boundary-zt": {"kid": "boundary-zt-1", "protected": BOUNDARY},
}


def gateway_iss(kid: str) -> str:
    """The `iss` a gateway stamps into the tokens it signs: `LocalIssuer::gateway_iss` in zero-trust-rs."""
    return f"spiffe://{TRUST_DOMAIN}/ns/zt-gateway/sa/{kid}"


def signing_key(kid: str) -> tuple:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    # PKCS#1 ("BEGIN RSA PRIVATE KEY"), what the gateway's signing_key_path loader reads.
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                    serialization.NoEncryption())
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_pem, jwk


def registry() -> dict:
    def workload(name: str, spiffe: str, callers: list) -> dict:
        return {"name": name, "spiffe_id": spiffe,
                "namespace": spiffe.split("/ns/")[1].split("/")[0],
                "service_account": spiffe.rsplit("/sa/", 1)[1], "max_obo_chain_depth": 2,
                "allowed_callers": callers, "bootstrap_token": secrets.token_urlsafe(24)}
    return {"trust_domain": TRUST_DOMAIN,
            "workloads": [workload("risk-review-agent", AGENT, []),
                          workload("boundary", BOUNDARY, [AGENT])]}


def sidecar_config(name: str, cfg: dict, *, admin_port: int, proxy: str, upstream: str, client_auth: str,
                   trusted: list, extra: dict) -> dict:
    config = {
        "proxy_addr": proxy,
        "admin_addr": f"127.0.0.1:{admin_port}",
        "upstream_addr": upstream,
        "registry_path": "/config/registry.yaml",
        "protected_workload": cfg["protected"],
        "token_ttl_seconds": 300,
        "tls": {"cert_path": "/config/server.pem", "key_path": "/config/server.key", "client_auth": client_auth},
        "ca": {"cert_path": "/config/ca.pem", "ttl_seconds": 3600},
        "signing_key_path": "/config/signing.pem",
        "jwks_path": "/config/jwks.json",
        "active_kid": cfg["kid"],
        "trusted_issuers": trusted,
        "user_issuers": [IDP_ISSUER],
        "user_idps": [{"issuer": IDP_ISSUER, "jwks_path": "/config/idp-jwks.json",
                       "audience": AUDIENCE, "principal_claim": "sub"}],
        "strict": True,
    }
    config.update(extra)
    return config


def copy_ca(target: Path, service: str) -> None:
    """The dev CA and the service's own TLS certificate, copied into the service's config directory."""
    (target / "ca.pem").write_bytes((CA_OUT / "ca" / "ca.pem").read_bytes())
    for name in ("server.pem", "server.key"):
        (target / name).write_bytes((CA_OUT / "services" / service / name).read_bytes())
    (target / "idp-jwks.json").write_text(IDP_JWKS.read_text())


def write(path: Path, data, *, private: bool = False) -> None:
    """Write data as the format its file name says: .json as JSON, .yaml as YAML, anything else as given."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (bytes, str)):
        text = data
    elif path.suffix == ".json":
        text = json.dumps(data, indent=2) + "\n"
    else:
        text = yaml.safe_dump(data, sort_keys=False)
    path.write_bytes(text.encode() if isinstance(text, str) else text)
    if private:
        path.chmod(0o600)


def main() -> None:
    if not IDP_JWKS.exists() or not (CA_OUT / "ca" / "ca.pem").exists():
        sys.exit("run `make trust-keys` first: it creates the dev CA and the IdP keys")
    # Start clean, so a rerun cannot leave a stale signing key or registry behind.
    shutil.rmtree(OUT, ignore_errors=True)

    keys = {}
    for name, cfg in SIDECARS.items():
        keys[name] = signing_key(cfg["kid"])
    public = {name: {"keys": [keys[name][1]]} for name in SIDECARS}
    reg = registry()
    capability = {
        "default": "deny",
        "rules": [
            {"method": method, "path": path, "users": ANALYSTS, "workloads": [AGENT]}
            for method, path in (("GET", "/products/*/rows"), ("POST", "/products/*/sparql"),
                                 ("POST", "/products/*/proposals"))
        ],
    }

    # agent-zt: edge mint and token exchange, on loopback. The proxy is unused: its port is loopback-only.
    agent_dir = OUT / "agent-zt"
    write(agent_dir / "signing.pem", keys["agent-zt"][0], private=True)
    write(agent_dir / "jwks.json", public["agent-zt"])
    write(agent_dir / "registry.yaml", reg)
    copy_ca(agent_dir, "agent-zt")
    write(agent_dir / "gateway.yaml", sidecar_config(
        "agent-zt", SIDECARS["agent-zt"], admin_port=6443, proxy="127.0.0.1:8445",
        upstream="http://127.0.0.1:9", client_auth="optional",
        trusted=[gateway_iss("agent-zt-1")], extra={"gateway_id": AGENT}))

    # boundary-zt: verifies the agent's tokens (its own key and the agent's public key), serves the agent over mTLS,
    # forwards the verified token to the boundary's loopback listener, and enforces the capability policy.
    bz_dir = OUT / "boundary-zt"
    write(bz_dir / "signing.pem", keys["boundary-zt"][0], private=True)
    write(bz_dir / "jwks.json", {"keys": [keys["boundary-zt"][1], keys["agent-zt"][1]]})
    write(bz_dir / "registry.yaml", reg)
    write(bz_dir / "capability.yaml", capability)
    copy_ca(bz_dir, "boundary-zt")
    write(bz_dir / "gateway.yaml", sidecar_config(
        "boundary-zt", SIDECARS["boundary-zt"], admin_port=6445, proxy="0.0.0.0:8444",
        upstream="http://127.0.0.1:8080", client_auth="required",
        trusted=[gateway_iss("agent-zt-1")],
        extra={"capability_policy_path": "/config/capability.yaml", "jti_cache_enabled": True,
               "forward_verified_token": True}))

    # The boundary's own check of the forwarded token: the gateways it trusts, with their public keys.
    write(OUT / "boundary" / "gateways.json", {"gateways": [
        {"issuer": gateway_iss("agent-zt-1"), "jwks": public["agent-zt"]},
        {"issuer": gateway_iss("boundary-zt-1"), "jwks": public["boundary-zt"]},
    ]})

    # The agent's client certificate, for its admin and proxy calls.
    agent_certs = OUT / "agent"
    for name in ("risk-review-agent.pem", "risk-review-agent.key"):
        (agent_certs / name).parent.mkdir(parents=True, exist_ok=True)
        (agent_certs / name).write_bytes((CA_OUT / name).read_bytes())
    (agent_certs / "ca.pem").write_bytes((CA_OUT / "ca" / "ca.pem").read_bytes())

    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
