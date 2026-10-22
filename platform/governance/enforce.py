import os
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import httpx

from shared.compliance.masking import ColumnMaskingPolicy, DataMasker

OPA_MASKING_URL = os.getenv(
    "OPA_MASKING_URL", "http://opa:8181/v1/data/data_mesh/access/masking_strategy"
)
ES_URL = os.getenv("ES_URL", "http://elasticsearch:9200")
AUDIT_INDEX = "governance-audit"


class OPAError(Exception):
    """OPA gave no valid masking decision; the read must fail."""


async def opa_decide_strategy(user_role: str, column_classification: Optional[str]) -> str:
    """Ask OPA which masking strategy applies. Raises OPAError on any failure."""
    payload = {
        "input": {"user_role": user_role, "column_classification": column_classification}
    }
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(OPA_MASKING_URL, json=payload)
    except httpx.HTTPError as exc:
        raise OPAError(f"OPA unreachable: {exc}") from exc

    if response.status_code != 200:
        raise OPAError(f"OPA returned HTTP {response.status_code}")

    try:
        strategy = response.json()["result"]
    except (ValueError, KeyError, TypeError) as exc:
        raise OPAError("OPA response has no result") from exc

    if not isinstance(strategy, str):
        raise OPAError("OPA masking strategy is malformed")
    return strategy


async def elasticsearch_write_audit(record: dict) -> None:
    """Write one audit record. Raises on any failure, so the read is denied."""
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.post(f"{ES_URL}/{AUDIT_INDEX}/_doc", json=record)
    response.raise_for_status()


async def mask_rows(
    rows: list,
    table: str,
    columns: list,
    user_id: str,
    user_role: str,
    policy: ColumnMaskingPolicy,
    *,
    decide_strategy: Callable[[str, Optional[str]], Awaitable[str]] = opa_decide_strategy,
    write_audit: Callable[[dict], Awaitable[None]] = elasticsearch_write_audit,
) -> list:
    """Mask the requested columns of each row, then audit the read before returning.

    Any exception (OPA failure, unknown strategy, audit failure) propagates, so no
    rows are returned when the read cannot be decided or recorded.
    """
    # Every key in a row is decided, not only the requested columns: an unrequested
    # column with no classification is masked like any other unclassified column.
    keys = list(dict.fromkeys([*columns, *(key for row in rows for key in row)]))
    strategies = {}
    for key in keys:
        classification = policy.get_column_classification(table, key)
        strategies[key] = await decide_strategy(user_role, classification)

    masked = []
    for row in rows:
        masked_row = {}
        for key, value in row.items():
            strategy = strategies[key]
            if strategy == "no_mask":
                masked_row[key] = value
            else:
                masked_row[key] = DataMasker.apply(strategy, str(value))
        masked.append(masked_row)

    await write_audit(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "user_role": user_role,
            "table": table,
            "columns": columns,
            "strategies": strategies,
            "row_count": len(rows),
        }
    )
    return masked
