"""Shared database handle for the web backend.

One shared read-only connection to the DuckDB database, plus a fresh *cursor*
per request. DuckDB cursors created from one connection are independent and can
run concurrently across threads (FastAPI runs sync endpoints in a threadpool),
so requests no longer serialize behind a single global lock — DuckDB handles
concurrent readers itself.
"""
from __future__ import annotations

import eurodata

_shared: eurodata.EuroData | None = None


def _shared_handle() -> eurodata.EuroData:
    """The process-wide read-only handle (opened once)."""
    global _shared
    if _shared is None:
        _shared = eurodata.EuroData()  # read_only=True by default
    return _shared


def get_ed() -> eurodata.EuroData:
    """A per-request EuroData handle backed by its own cursor over the shared
    read-only connection. Cheap to create; safe to use concurrently with the
    cursors handed to other in-flight requests."""
    return eurodata.EuroData.from_connection(_shared_handle().con.cursor())


def reset() -> None:
    """Drop the shared handle (tests point DUCKDB_PATH elsewhere)."""
    global _shared
    if _shared is not None:
        _shared.close()
    _shared = None
