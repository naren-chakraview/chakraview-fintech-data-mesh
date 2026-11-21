"""Reads product rows. The demo profile reads fixture snapshots; a pyiceberg reader is the production adapter.

A snapshot is the exact bytes of the fixture file. Lineage verifies those bytes.
"""

import json
from pathlib import Path
from typing import List, Optional


class UnknownColumn(ValueError):
    """A requested column is not in the product. The caller answers 400."""


class FixtureReader:
    """Reads the current snapshot of each product. A product written by the boundary (a direct write, or an accepted
    proposal) is read from the state directory, which holds the boundary's own snapshots and is never committed.
    Everything else is read from the fixtures."""

    def __init__(self, fixtures_dir: Path, state_dir: Optional[Path] = None):
        self.fixtures_dir = Path(fixtures_dir)
        self.state_dir = Path(state_dir) if state_dir else None

    def _path(self, product_id: str) -> Path:
        if self.state_dir is not None and (self.state_dir / f"{product_id}.json").exists():
            return self.state_dir / f"{product_id}.json"
        path = self.fixtures_dir / f"{product_id}.json"
        if not path.exists():
            raise LookupError(f"no snapshot for {product_id}")
        return path

    def snapshot(self, product_id: str) -> bytes:
        return self._path(product_id).read_bytes()

    def columns(self, product_id: str) -> List[str]:
        return list(json.loads(self.snapshot(product_id))["columns"])

    def read(self, product_id: str, columns: List[str]) -> List[dict]:
        document = json.loads(self.snapshot(product_id))
        known = set(document["columns"])
        unknown = [c for c in columns if c not in known]
        if unknown:
            raise UnknownColumn(f"unknown columns: {', '.join(unknown)}")
        return [{c: row[c] for c in columns} for row in document["rows"]]
