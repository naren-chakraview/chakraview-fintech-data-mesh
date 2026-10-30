"""Contract test: every customer-IRI code path matches the golden vectors.

The vectors in semantics/core/identity-vectors.json were produced by an
independent stdlib implementation, not by the library. A domain that mints
or resolves customer IRIs differently fails here.
"""

import json

import pytest

from shared.semantic.identity import KEY_ENV_VAR, IriKeyMissingError, mint_customer_iri
from shared.semantic.paths import REPO_ROOT

VECTORS = json.loads((REPO_ROOT / "semantics/core/identity-vectors.json").read_text(encoding="utf-8"))
KEY = VECTORS["test_only_key"]
CASES = VECTORS["vectors"]
CASE_IDS = [case["id"] for case in CASES]


@pytest.fixture
def test_key_in_env(monkeypatch):
    monkeypatch.setenv(KEY_ENV_VAR, KEY)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_library_matches_golden_vector(case):
    iri = mint_customer_iri(case["email"], case["kyc_id"], key=KEY, base_url=VECTORS["base_url"])
    assert iri == case["expected_iri"]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
@pytest.mark.parametrize("domain", ["accounts", "risk", "transactions"])
def test_domain_path_matches_golden_vector(case, domain, domain_resolver_classes, test_key_in_env):
    resolver = domain_resolver_classes[domain]()
    if domain == "accounts":
        iri = resolver.mint_customer_iri(case["email"], case["kyc_id"])
    else:
        iri = resolver.resolve_customer_iri(case["email"], case["kyc_id"])
    assert iri == case["expected_iri"], f"{domain} drifted from the identity rule"


def test_d4_collision_pair_mints_different_iris():
    pair = [c for c in CASES if c["id"].startswith("d4-collision-pair")]
    assert len(pair) == 2
    assert pair[0]["expected_iri"] != pair[1]["expected_iri"]


def test_iris_are_full_256_bit_digests():
    for case in CASES:
        digest = case["expected_iri"].split("#")[1]
        assert len(digest) == 64
        assert all(ch in "0123456789abcdef" for ch in digest)


def test_missing_key_refuses_to_mint(monkeypatch):
    monkeypatch.delenv(KEY_ENV_VAR, raising=False)
    with pytest.raises(IriKeyMissingError):
        mint_customer_iri("john@acme.com", "kyc_123")


def test_key_rotation_remints_every_customer(monkeypatch):
    before = mint_customer_iri("john@acme.com", "kyc_123", key=KEY)
    after = mint_customer_iri("john@acme.com", "kyc_123", key=KEY + "-rotated")
    assert before != after
