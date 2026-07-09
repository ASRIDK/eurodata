"""Fetch all registered sources and load into DuckDB."""
from importlib import import_module

from _bootstrap import ensure_paths

ensure_paths()

for module_name in (
    "eurodata.sources.eurostat",
    "eurodata.sources.ecb",
    "eurodata.sources.oecd",
    "eurodata.sources.world_bank",
):
    import_module(module_name)
from eurodata.config import get_settings
from eurodata.db import connect
from eurodata.ingest.pipeline import run_all

if __name__ == "__main__":
    con = connect()
    try:
        results = run_all(con, get_settings().ingest_start_year)
        for source, count in results.items():
            print(f"{source}: {count} records")
    finally:
        con.close()
