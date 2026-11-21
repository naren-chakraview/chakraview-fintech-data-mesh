"""Rate limits for proposals, per agent and per person. A sliding window in memory (production: the shared store)."""

from datetime import datetime, timedelta
from typing import Dict, List


class RateLimited(Exception):
    def __init__(self, key: str):
        super().__init__(f"rate limit reached for {key}")
        self.key = key


class RateLimiter:
    def __init__(self, limit: int, window: timedelta):
        self.limit = limit
        self.window = window
        self._hits: Dict[str, List[datetime]] = {}

    def take(self, key: str, now: datetime) -> None:
        """Record one proposal for key, or raise RateLimited when the window is full. Nothing is recorded on refusal."""
        recent = [t for t in self._hits.get(key, []) if now - t < self.window]
        if len(recent) >= self.limit:
            self._hits[key] = recent
            raise RateLimited(key)
        recent.append(now)
        self._hits[key] = recent
