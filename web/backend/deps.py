"""Shared database handle for the web backend.

One read-only EuroData handle per process. DuckDB connections are not safe
for concurrent queries from multiple threads (FastAPI runs sync endpoints in
a threadpool), so every query must run under `lock`.
"""
from __future__ import annotations

import threading

import eurodata

lock = threading.Lock()
_handle: eurodata.EuroData | None = None


def get_ed() -> eurodata.EuroData:
    global _handle
    if _handle is None:
        _handle = eurodata.EuroData()  # read_only=True by default
    return _handle


def reset() -> None:
    """Drop the cached handle (tests point DUCKDB_PATH elsewhere)."""
    global _handle
    if _handle is not None:
        _handle.close()
    _handle = None
