import asyncio
import hashlib
import sys
from pathlib import Path

import httpx
import pytest

# platform/governance is not a package importable as platform.governance (the stdlib
# platform module shadows it), so import enforce from its own directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform" / "governance"))

import enforce  # noqa: E402
from enforce import OPAError, mask_rows, opa_decide_strategy  # noqa: E402
from shared.compliance.masking import ColumnMaskingPolicy  # noqa: E402

TABLE = "accounts.account_balances"
ROWS = [
    {"account_id": "ACC-1001", "balance": "250.00"},
    {"account_id": "ACC-1002", "balance": "75.10"},
    {"account_id": "ACC-1003", "balance": "0.00"},
]


def stub_decide(strategy, seen=None):
    async def decide(user_role, classification):
        if seen is not None:
            seen.append((user_role, classification))
        if isinstance(strategy, Exception):
            raise strategy
        return strategy

    return decide


def recording_audit(records, exc=None):
    async def audit(record):
        if exc is not None:
            raise exc
        records.append(record)

    return audit


def read(rows, columns, decide, audit, policy=None):
    return asyncio.run(
        mask_rows(
            rows,
            TABLE,
            columns,
            "u-1",
            "risk_analyst",
            policy or ColumnMaskingPolicy(),
            decide_strategy=decide,
            write_audit=audit,
        )
    )


def test_unclassified_column_is_hashed_on_read():
    seen, records = [], []

    out = read(
        [{"account_id": "ACC-1001"}],
        ["account_id"],
        stub_decide("full_hash", seen),
        recording_audit(records),
    )

    assert out[0]["account_id"] == hashlib.sha256(b"ACC-1001").hexdigest()
    assert seen == [("risk_analyst", None)]


def test_public_column_is_returned_unchanged():
    out = read(
        ROWS,
        ["account_id"],
        stub_decide("no_mask"),
        recording_audit([]),
    )

    assert [row["account_id"] for row in out] == ["ACC-1001", "ACC-1002", "ACC-1003"]


def test_one_audit_record_per_read():
    records = []

    read(ROWS, ["account_id"], stub_decide("full_hash"), recording_audit(records))

    assert len(records) == 1
    record = records[0]
    assert record["user_id"] == "u-1"
    assert record["user_role"] == "risk_analyst"
    assert record["table"] == TABLE
    assert record["columns"] == ["account_id"]
    assert record["strategies"] == {"account_id": "full_hash"}


def test_opa_error_returns_no_rows():
    records = []

    with pytest.raises(OPAError):
        read(ROWS, ["account_id"], stub_decide(OPAError("down")), recording_audit(records))

    assert records == []


def test_audit_failure_returns_no_rows():
    with pytest.raises(RuntimeError):
        read(
            ROWS,
            ["account_id"],
            stub_decide("full_hash"),
            recording_audit([], exc=RuntimeError("elasticsearch down")),
        )


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        read(ROWS, ["account_id"], stub_decide("show_everything"), recording_audit([]))


def use_opa(monkeypatch, handler):
    """Route the real OPA client through a mock transport for one test."""
    real_client = httpx.AsyncClient

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), timeout=kwargs.get("timeout"))

    monkeypatch.setattr(enforce.httpx, "AsyncClient", client)


def test_opa_decide_returns_strategy(monkeypatch):
    use_opa(monkeypatch, lambda request: httpx.Response(200, json={"result": "partial_mask"}))

    assert asyncio.run(opa_decide_strategy("analyst", "sensitive")) == "partial_mask"


def test_opa_non_200_raises(monkeypatch):
    use_opa(monkeypatch, lambda request: httpx.Response(500, json={}))

    with pytest.raises(OPAError):
        asyncio.run(opa_decide_strategy("analyst", "sensitive"))


def test_opa_missing_result_raises(monkeypatch):
    use_opa(monkeypatch, lambda request: httpx.Response(200, json={}))

    with pytest.raises(OPAError):
        asyncio.run(opa_decide_strategy("analyst", "sensitive"))


def test_opa_unreachable_returns_no_rows(monkeypatch):
    def unreachable(request):
        raise httpx.ConnectError("connection refused", request=request)

    use_opa(monkeypatch, unreachable)
    records = []

    with pytest.raises(OPAError):
        asyncio.run(
            mask_rows(ROWS, TABLE, ["account_id"], "u-1", "risk_analyst",
                      ColumnMaskingPolicy(), write_audit=recording_audit(records))
        )

    assert records == []
