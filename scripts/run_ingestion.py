"""Fetch all registered sources and load into DuckDB."""
import eurodata.sources.eurostat  # noqa: F401  (register fetchers)
import eurodata.sources.ecb       # noqa: F401
import eurodata.sources.oecd      # noqa: F401
import eurodata.sources.world_bank  # noqa: F401
from eurodata.config import get_settings
from eurodata.db import connect
from eurodata.ingest.pipeline import run_all

if __name__ == "__main__":
    con = connect()
    results = run_all(con, get_settings().ingest_start_year)
    for source, count in results.items():
        print(f"{source}: {count} records")
