from importlib import resources
from pathlib import Path

import duckdb

from eurodata.config import get_settings

_SEQUENCES = ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    for seq in _SEQUENCES:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    sql = resources.files("eurodata.model").joinpath("schema.sql").read_text()
    con.execute(sql)


def connect(path: str | None = None) -> duckdb.DuckDBPyConnection:
    db_path = path or get_settings().duckdb_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    init_schema(con)
    return con
