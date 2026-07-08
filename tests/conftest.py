import duckdb
import pytest


@pytest.fixture
def memdb():
    """In-memory DuckDB connection for tests."""
    con = duckdb.connect(":memory:")
    yield con
    con.close()
