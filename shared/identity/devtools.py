"""Development-only key and certificate helpers. Production uses the company IdP (OIDC) and SPIRE.

Nothing here runs in production. Generated material is written under gitignored directories.
"""

import datetime as dt
import json
import uuid
from typing import Iterable, Optional, Tuple

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def generate_rsa_keypair() -> Tuple[bytes, dict]:
    """Return (private key PEM, public JWK with kid) for an RS256 signing key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": f"dev-{uuid.uuid4().hex[:12]}", "use": "sig", "alg": "RS256"})
    return private_pem, jwk


def mint_token(
    private_pem: bytes,
    kid: str,
    *,
    issuer: str,
    audience: str,
    subject: str,
    roles: Iterable[str] = (),
    owns: Iterable[str] = (),
    ttl_seconds: int = 3600,
    now: Optional[dt.datetime] = None,
    extra_claims: Optional[dict] = None,
) -> str:
    issued = now or dt.datetime.now(dt.timezone.utc)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": int(issued.timestamp()),
        "nbf": int(issued.timestamp()),
        "exp": int((issued + dt.timedelta(seconds=ttl_seconds)).timestamp()),
        "roles": list(roles),
        "owns": list(owns),
    }
    claims.update(extra_claims or {})
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})


def make_ca(common_name: str = "chakra dev workload CA") -> Tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_cert_sign=True, crl_sign=True,
            content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def issue_workload_cert(
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    spiffe_id: str,
    days: int = 30,
) -> Tuple[bytes, bytes]:
    """Issue a client certificate whose only URI SAN is the SPIFFE ID. Returns (key PEM, cert PEM)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, spiffe_id.rsplit("/", 1)[-1])])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier(spiffe_id)]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return (
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        cert.public_bytes(serialization.Encoding.PEM),
    )


def issue_server_cert(
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    dns_names: Iterable[str],
    days: int = 30,
) -> Tuple[bytes, bytes]:
    """Issue the gateway's TLS server certificate for the given DNS names. Returns (key PEM, cert PEM)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    names = list(dns_names)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return (
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        cert.public_bytes(serialization.Encoding.PEM),
    )
