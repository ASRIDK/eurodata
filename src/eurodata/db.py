from importlib import resources
from pathlib import Path

import duckdb

from eurodata.config import get_settings

_SEQUENCES = ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run",
              "seq_ingestion_error", "seq_event"]

# Additive upgrades for databases created before these columns existed.
_MIGRATIONS = [
    "ALTER TABLE indicator ADD COLUMN IF NOT EXISTS definition VARCHAR",
    "ALTER TABLE indicator ADD COLUMN IF NOT EXISTS is_proxy BOOLEAN DEFAULT FALSE",
    "ALTER TABLE indicator ADD COLUMN IF NOT EXISTS proxy_note VARCHAR",
]


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    for seq in _SEQUENCES:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    sql = resources.files("eurodata.model").joinpath("schema.sql").read_text()
    con.execute(sql)
    for stmt in _MIGRATIONS:
        con.execute(stmt)


def connect(path: str | None = None, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = path or get_settings().duckdb_path
    if not read_only:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path, read_only=read_only)
    if not read_only:
        init_schema(con)
    return con
