"""Lineage attestations: a statement verifies for the snapshot it names, and fails for anything else."""

import base64
import copy
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform"))

from lineage.attest import build_statement, generate_signing_key, sign_envelope  # noqa: E402
from lineage.verify import LineageError, verify_envelope, verify_snapshot  # noqa: E402

PRODUCT = "risk-compliance.risk-scores"
SNAPSHOT = b'{"columns": ["a"], "rows": [{"a": "1"}]}'
PRODUCER = "spiffe://chakracommerce.com/ns/risk/sa/producer"


@pytest.fixture
def keys():
    private_pem, public_pem = generate_signing_key()
    private = serialization.load_pem_private_key(private_pem, password=None)
    public = serialization.load_pem_public_key(public_pem)
    return private, public


def envelope_for(private, snapshot=SNAPSHOT, product=PRODUCT):
    statement = build_statement(product, snapshot, PRODUCER, "abc123", [])
    return sign_envelope(statement, private, "producer-dev")


def test_matching_snapshot_verifies(keys):
    private, public = keys

    assert verify_snapshot(envelope_for(private), public, SNAPSHOT, PRODUCT) is True


def test_one_flipped_byte_fails(keys):
    private, public = keys
    tampered = SNAPSHOT.replace(b'"1"', b'"2"')

    assert verify_snapshot(envelope_for(private), public, tampered, PRODUCT) is False


def test_wrong_signing_key_fails(keys):
    _, public = keys
    other = Ed25519PrivateKey.generate()

    assert verify_snapshot(envelope_for(other), public, SNAPSHOT, PRODUCT) is False


def test_statement_for_another_product_fails(keys):
    private, public = keys

    assert verify_snapshot(envelope_for(private, product="accounts.account-master"), public, SNAPSHOT, PRODUCT) is False


def test_tampered_payload_fails_signature(keys):
    private, public = keys
    envelope = envelope_for(private)
    statement = json.loads(base64.b64decode(envelope["payload"]))
    statement["predicate"]["producer"] = "spiffe://chakracommerce.com/ns/evil/sa/x"
    envelope = copy.deepcopy(envelope)
    envelope["payload"] = base64.b64encode(json.dumps(statement, sort_keys=True, separators=(",", ":")).encode()).decode()

    with pytest.raises(LineageError):
        verify_envelope(envelope, public)


@pytest.mark.parametrize("mutate", [
    lambda e: e.pop("signatures"),
    lambda e: e.update(payloadType="text/plain"),
    lambda e: e.update(payload="!!not base64!!"),
    lambda e: e["signatures"].clear(),
])
def test_malformed_envelope_fails_closed(keys, mutate):
    private, public = keys
    envelope = copy.deepcopy(envelope_for(private))
    mutate(envelope)

    assert verify_snapshot(envelope, public, SNAPSHOT, PRODUCT) is False


def test_statement_has_the_predicate_type_and_digest(keys):
    private, _ = keys
    statement = verify_envelope(envelope_for(private), keys[1])

    assert statement["_type"] == "https://in-toto.io/Statement/v1"
    assert statement["predicateType"] == "https://chakracommerce.com/data-provenance/v1"
    assert statement["subject"][0]["name"] == PRODUCT
    assert len(statement["subject"][0]["digest"]["sha256"]) == 64
