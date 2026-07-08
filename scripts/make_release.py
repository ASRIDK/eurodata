"""Produce a versioned release bundle of redistributable data."""
from pathlib import Path

from eurodata.config import get_settings
from eurodata.db import connect
from eurodata.export.release import export_facts

if __name__ == "__main__":
    con = connect()
    out_dir = Path(get_settings().release_dir) / "eurodata-v1"
    path = export_facts(con, out_dir)
    print(f"Wrote {path}")
