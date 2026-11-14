"""A person is a verified JWT; a workload is a verified SPIFFE ID. Nothing else is trusted."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from shared.identity import AuthError, CallerVerifier, IdentityError, JWKSCache, spiffe_id_from_pem, verify_token  # noqa: E402
from shared.identity.devtools import generate_rsa_keypair, issue_workload_cert, make_ca, mint_token  # noqa: E402

ISS = "http://dev-idp"
AUD = "data-mesh"
SPIFFE = "spiffe://chakracommerce.com/ns/analytics/sa/notebook"


@pytest.fixture(scope="module")
def idp():
    private_pem, jwk = generate_rsa_keypair()
    return private_pem, jwk, {"keys": [jwk]}


def good(idp, **overrides):
    private_pem, jwk, _ = idp
    kwargs = dict(issuer=ISS, audience=AUD, subject="a@chakra.fintech", roles=["analyst"])
    kwargs.update(overrides)
    return mint_token(private_pem, jwk["kid"], **kwargs)


def test_valid_token_yields_subject_and_roles(idp):
    principal = verify_token(good(idp), idp[2], issuer=ISS, audience=AUD)

    assert principal.subject == "a@chakra.fintech"
    assert principal.roles == frozenset({"analyst"})


def test_wrong_audience_is_rejected(idp):
    with pytest.raises(AuthError):
        verify_token(good(idp, audience="someone-else"), idp[2], issuer=ISS, audience=AUD)


def test_wrong_issuer_is_rejected(idp):
    with pytest.raises(AuthError):
        verify_token(good(idp, issuer="http://evil"), idp[2], issuer=ISS, audience=AUD)


def test_expired_token_is_rejected(idp):
    issued = datetime.now(timezone.utc) - timedelta(hours=3)
    with pytest.raises(AuthError):
        verify_token(good(idp, now=issued, ttl_seconds=60), idp[2], issuer=ISS, audience=AUD)


def test_token_not_yet_valid_is_rejected(idp):
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    with pytest.raises(AuthError):
        verify_token(good(idp, now=future), idp[2], issuer=ISS, audience=AUD)


def test_token_signed_by_another_key_is_rejected(idp):
    other_pem, other_jwk = generate_rsa_keypair()
    forged = mint_token(other_pem, idp[1]["kid"], issuer=ISS, audience=AUD, subject="x", roles=["risk_analyst"])
    with pytest.raises(AuthError):
        verify_token(forged, idp[2], issuer=ISS, audience=AUD)


def test_unknown_key_id_is_rejected(idp):
    private_pem, _, _ = idp
    token = mint_token(private_pem, "not-a-real-kid", issuer=ISS, audience=AUD, subject="x")
    with pytest.raises(AuthError):
        verify_token(token, idp[2], issuer=ISS, audience=AUD)


def test_hs256_token_is_rejected(idp):
    token = jwt.encode({"iss": ISS, "aud": AUD, "sub": "x", "exp": 9999999999, "iat": 0, "nbf": 0},
                       "shared-secret", algorithm="HS256", headers={"kid": idp[1]["kid"]})
    with pytest.raises(AuthError):
        verify_token(token, idp[2], issuer=ISS, audience=AUD)


def test_none_algorithm_is_rejected(idp):
    token = jwt.encode({"iss": ISS, "aud": AUD, "sub": "x", "exp": 9999999999, "iat": 0, "nbf": 0},
                       key=None, algorithm="none")
    with pytest.raises(AuthError):
        verify_token(token, idp[2], issuer=ISS, audience=AUD)


def test_malformed_roles_claim_is_rejected(idp):
    private_pem, jwk, _ = idp
    token = mint_token(private_pem, jwk["kid"], issuer=ISS, audience=AUD, subject="x", roles=[])
    claims = jwt.decode(token, options={"verify_signature": False})
    claims["roles"] = "analyst"
    bad = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": jwk["kid"]})
    with pytest.raises(AuthError):
        verify_token(bad, idp[2], issuer=ISS, audience=AUD)


def test_empty_token_is_rejected(idp):
    with pytest.raises(AuthError):
        verify_token("", idp[2], issuer=ISS, audience=AUD)


def test_spiffe_id_is_read_from_uri_san():
    ca_key, ca_cert = make_ca()
    _, cert_pem = issue_workload_cert(ca_key, ca_cert, SPIFFE)

    assert spiffe_id_from_pem(cert_pem.decode()) == SPIFFE


def test_spiffe_id_accepts_url_escaped_pem_from_gateway():
    ca_key, ca_cert = make_ca()
    _, cert_pem = issue_workload_cert(ca_key, ca_cert, SPIFFE)

    assert spiffe_id_from_pem(quote(cert_pem.decode())) == SPIFFE


def test_certificate_without_san_is_rejected():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    import datetime as dt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "no-san")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + dt.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    with pytest.raises(IdentityError):
        spiffe_id_from_pem(cert.public_bytes(serialization.Encoding.PEM).decode())


def test_two_spiffe_ids_are_rejected():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    import datetime as dt

    ca_key, ca_cert = make_ca()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "x")]))
            .issuer_name(ca_cert.subject).public_key(key.public_key()).serial_number(2)
            .not_valid_before(now).not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([
                x509.UniformResourceIdentifier("spiffe://a/b"),
                x509.UniformResourceIdentifier("spiffe://c/d"),
            ]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    with pytest.raises(IdentityError):
        spiffe_id_from_pem(cert.public_bytes(serialization.Encoding.PEM).decode())


@pytest.mark.parametrize("pem", ["", "not a certificate", "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"])
def test_garbage_certificate_is_rejected(pem):
    with pytest.raises(IdentityError):
        spiffe_id_from_pem(pem)


def test_caller_needs_both_token_and_certificate(idp):
    async def fetch(url):
        return idp[2]

    verifier = CallerVerifier(jwks=JWKSCache("unused", fetch=fetch), issuer=ISS, audience=AUD)
    ca_key, ca_cert = make_ca()
    _, cert_pem = issue_workload_cert(ca_key, ca_cert, SPIFFE)
    token = good(idp)

    caller = asyncio.run(verifier.verify({"authorization": f"Bearer {token}",
                                          "x-client-cert": quote(cert_pem.decode())}))
    assert caller.spiffe_id == SPIFFE

    for headers in ({"x-client-cert": quote(cert_pem.decode())},
                    {"authorization": f"Bearer {token}"},
                    {"authorization": f"Basic {token}", "x-client-cert": quote(cert_pem.decode())}):
        with pytest.raises(AuthError):
            asyncio.run(verifier.verify(headers))


def test_jwks_failure_is_not_cached_as_a_key():
    calls = []

    async def failing(url):
        calls.append(url)
        raise AuthError("JWKS endpoint returned HTTP 500")

    cache = JWKSCache("http://idp/jwks", fetch=failing)
    with pytest.raises(AuthError):
        asyncio.run(cache.get())
    with pytest.raises(AuthError):
        asyncio.run(cache.get())
    assert len(calls) == 2
