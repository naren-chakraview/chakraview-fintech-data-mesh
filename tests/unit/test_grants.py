"""Grants are stored, scoped, expiring and checked at read time."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.governance.grants import MemoryGrantStore, PostgresGrantStore  # noqa: E402

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
SCOPE = dict(subject="a@chakra.fintech", workload_spiffe_id="spiffe://x/ns/a/sa/n",
             product_id="risk-compliance.risk-scores", purpose="fraud-review")


@pytest.fixture
def store():
    s = MemoryGrantStore()
    s.create(columns=["fraud_score", "account_ref"], expires_at=NOW + timedelta(hours=1), **SCOPE)
    return s


def lookup(store, **overrides):
    args = dict(SCOPE, columns=["fraud_score"], now=NOW)
    args.update(overrides)
    return store.find_valid(**args)


def test_matching_grant_is_found(store):
    assert lookup(store) is not None


def test_expired_grant_is_not_found(store):
    assert lookup(store, now=NOW + timedelta(hours=2)) is None


def test_wrong_subject_is_not_found(store):
    assert lookup(store, subject="other@chakra.fintech") is None


def test_wrong_workload_is_not_found(store):
    assert lookup(store, workload_spiffe_id="spiffe://x/ns/batch/sa/nightly") is None


def test_wrong_product_is_not_found(store):
    assert lookup(store, product_id="accounts.account-master") is None


def test_wrong_purpose_is_not_found(store):
    assert lookup(store, purpose="marketing") is None


def test_column_outside_grant_is_not_found(store):
    assert lookup(store, columns=["fraud_score", "balance"]) is None


def test_no_grant_is_not_found():
    assert lookup(MemoryGrantStore()) is None


def test_grant_to_dict_lists_scope(store):
    grant = store.find_valid(columns=["fraud_score"], now=NOW, **SCOPE)
    data = grant.to_dict()

    assert data["columns"] == ["account_ref", "fraud_score"]
    assert data["purpose"] == "fraud-review"
    assert data["expires_at"].startswith("2026-11-14T13:00:00")


@pytest.mark.skipif(not os.getenv("POSTGRES_DSN"), reason="set POSTGRES_DSN to test the Postgres store")
def test_postgres_store_round_trip():
    store = PostgresGrantStore()
    grant = store.create(columns=["fraud_score"], expires_at=datetime.now(timezone.utc) + timedelta(hours=1), **SCOPE)

    found = store.find_valid(columns=["fraud_score"], now=datetime.now(timezone.utc), **SCOPE)

    assert found is not None and found.id == grant.id
