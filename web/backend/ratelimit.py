"""A tiny in-memory, per-key sliding-window rate limiter.

Scope is intentionally local/demo: `/api/chat` is unauthenticated and spends
money on model calls, so we cap requests per client IP within a window. This is
per-process (no shared store), which is fine for a single-instance demo; a
multi-instance deployment would swap in Redis or a gateway limiter.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> float | None:
        """Register a request for `key`. Returns None if allowed, or the number
        of seconds until a slot frees up (Retry-After) if the limit is hit."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self.window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                retry_after = self.window - (now - hits[0])
                return max(1.0, retry_after)
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def from_env() -> RateLimiter:
    """Build the /api/chat limiter from CHAT_RATE_LIMIT / CHAT_RATE_WINDOW
    (defaults: 20 requests per 60s)."""
    max_requests = int(os.environ.get("CHAT_RATE_LIMIT", "20"))
    window = float(os.environ.get("CHAT_RATE_WINDOW", "60"))
    return RateLimiter(max_requests, window)
