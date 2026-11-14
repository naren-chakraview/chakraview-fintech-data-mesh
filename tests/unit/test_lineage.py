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


# R3: the trust configuration, not the attestation directory, decides the key and the producer.
import json as _json  # noqa: E402

from lineage.attest import publish_attestation  # noqa: E402
from lineage.trust import load_trust, verify_product  # noqa: E402

REAL_PRODUCER = PRODUCER
FORGED_PRODUCER = "spiffe://chakracommerce.com/ns/evil/sa/x"


def trust_dir(tmp_path, public_pem, producer=REAL_PRODUCER):
    (tmp_path / "trust").mkdir()
    (tmp_path / "trust" / "risk-producer.pub").write_bytes(public_pem)
    (tmp_path / "trust" / "producers.json").write_text(_json.dumps({"products": {PRODUCT: {
        "producer": producer, "public_key": "risk-producer.pub"}}}))
    return tmp_path / "trust"


def sign_into(directory, private_pem, producer=REAL_PRODUCER, snapshot=SNAPSHOT):
    publish_attestation(PRODUCT, snapshot, private_key_pem=private_pem, keyid="risk-producer",
                        producer_spiffe_id=producer, code_commit="abc", input_snapshots=[], out_dir=directory)


def test_attestation_under_the_expected_key_and_producer_verifies(tmp_path):
    private_pem, public_pem = generate_signing_key()
    trust = load_trust(trust_dir(tmp_path, public_pem))
    sign_into(tmp_path, private_pem)

    assert verify_product(PRODUCT, SNAPSHOT, tmp_path, trust) is True


def test_wrong_producer_under_the_right_key_fails(tmp_path):
    private_pem, public_pem = generate_signing_key()
    trust = load_trust(trust_dir(tmp_path, public_pem))
    sign_into(tmp_path, private_pem, producer=FORGED_PRODUCER)

    assert verify_product(PRODUCT, SNAPSHOT, tmp_path, trust) is False


def test_attacker_who_rewrites_the_attestation_with_their_own_key_fails(tmp_path):
    _, public_pem = generate_signing_key()
    trust = load_trust(trust_dir(tmp_path, public_pem))
    attacker_private, _ = generate_signing_key()
    sign_into(tmp_path, attacker_private)

    assert verify_product(PRODUCT, SNAPSHOT, tmp_path, trust) is False


def test_product_with_no_trust_entry_fails(tmp_path):
    private_pem, public_pem = generate_signing_key()
    trust = load_trust(trust_dir(tmp_path, public_pem))
    sign_into(tmp_path, private_pem)

    assert verify_product("accounts.account-master", SNAPSHOT, tmp_path, trust) is False
