from pathlib import Path

import duckdb
import pytest

import eurodata as ed_mod


@pytest.fixture
def memdb():
    """In-memory DuckDB connection for tests."""
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture(scope="session")
def ed():
    """Handle on the real, built database; skips if it hasn't been built."""
    if not Path("data/eurodata.duckdb").exists():
        pytest.skip("requires the built database")
    return ed_mod.open()
