"""Grants: a stored, scoped, expiring permission created by an approval and checked at read time.

A grant is {id, subject, workload_spiffe_id, product_id, columns, purpose, expires_at}.
find_valid never returns an expired, wrong-subject, wrong-workload, wrong-product, wrong-purpose
or column-insufficient grant. Any store error propagates, so the read is denied.
"""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol


@dataclass(frozen=True)
class Grant:
    id: str
    subject: str
    workload_spiffe_id: str
    product_id: str
    columns: frozenset
    purpose: str
    expires_at: datetime

    def covers(self, *, subject: str, workload_spiffe_id: str, product_id: str,
               columns: List[str], purpose: str, now: datetime) -> bool:
        return (
            self.expires_at > now
            and self.subject == subject
            and self.workload_spiffe_id == workload_spiffe_id
            and self.product_id == product_id
            and self.purpose == purpose
            and set(columns) <= self.columns
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject": self.subject,
            "workload_spiffe_id": self.workload_spiffe_id,
            "product_id": self.product_id,
            "columns": sorted(self.columns),
            "purpose": self.purpose,
            "expires_at": self.expires_at.isoformat(),
        }


class GrantStore(Protocol):
    def create(self, *, subject: str, workload_spiffe_id: str, product_id: str,
               columns: List[str], purpose: str, expires_at: datetime) -> Grant: ...

    def find_valid(self, *, subject: str, workload_spiffe_id: str, product_id: str,
                   columns: List[str], purpose: str, now: datetime) -> Optional[Grant]: ...


class MemoryGrantStore:
    """In-process store for unit tests and the demos. Grants do not survive a restart."""

    def __init__(self) -> None:
        self._grants: Dict[str, Grant] = {}

    def create(self, *, subject, workload_spiffe_id, product_id, columns, purpose, expires_at) -> Grant:
        grant = Grant(
            id=f"grant_{uuid.uuid4().hex[:12]}",
            subject=subject,
            workload_spiffe_id=workload_spiffe_id,
            product_id=product_id,
            columns=frozenset(columns),
            purpose=purpose,
            expires_at=expires_at,
        )
        self._grants[grant.id] = grant
        return grant

    def find_valid(self, *, subject, workload_spiffe_id, product_id, columns, purpose, now) -> Optional[Grant]:
        for grant in self._grants.values():
            if grant.covers(subject=subject, workload_spiffe_id=workload_spiffe_id,
                            product_id=product_id, columns=columns, purpose=purpose, now=now):
                return grant
        return None


GRANTS_TABLE = """
CREATE TABLE IF NOT EXISTS grants (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    workload_spiffe_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    columns JSONB NOT NULL,
    purpose TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
)
"""


class PostgresGrantStore:
    """Grants in Postgres. Connects per call so a dropped connection cannot leave a stale grant."""

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.environ["POSTGRES_DSN"]
        with self._connect() as conn:
            conn.execute(GRANTS_TABLE)

    def _connect(self):
        import psycopg  # imported here so the in-memory store works without psycopg installed

        return psycopg.connect(self.dsn, autocommit=True)

    def create(self, *, subject, workload_spiffe_id, product_id, columns, purpose, expires_at) -> Grant:
        grant = Grant(
            id=f"grant_{uuid.uuid4().hex[:12]}",
            subject=subject,
            workload_spiffe_id=workload_spiffe_id,
            product_id=product_id,
            columns=frozenset(columns),
            purpose=purpose,
            expires_at=expires_at,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO grants (id, subject, workload_spiffe_id, product_id, columns, purpose, expires_at)"
                " VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)",
                (grant.id, subject, workload_spiffe_id, product_id, json.dumps(sorted(columns)),
                 purpose, expires_at),
            )
        return grant

    def find_valid(self, *, subject, workload_spiffe_id, product_id, columns, purpose, now) -> Optional[Grant]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, subject, workload_spiffe_id, product_id, columns, purpose, expires_at"
                " FROM grants WHERE subject = %s AND workload_spiffe_id = %s AND product_id = %s"
                " AND purpose = %s AND expires_at > %s",
                (subject, workload_spiffe_id, product_id, purpose, now),
            ).fetchall()
        for row in rows:
            grant = Grant(
                id=row[0], subject=row[1], workload_spiffe_id=row[2], product_id=row[3],
                columns=frozenset(row[4]), purpose=row[5], expires_at=row[6],
            )
            if grant.covers(subject=subject, workload_spiffe_id=workload_spiffe_id,
                            product_id=product_id, columns=columns, purpose=purpose, now=now):
                return grant
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
