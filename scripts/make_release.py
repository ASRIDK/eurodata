"""Produce a versioned release bundle of redistributable data."""
from pathlib import Path

from _bootstrap import ensure_paths

ensure_paths()

import eurodata
from eurodata.config import get_settings
from eurodata.db import connect
from eurodata.export.release import export_facts

if __name__ == "__main__":
    con = connect(read_only=True)
    try:
        out_dir = Path(get_settings().release_dir) / f"eurodata-v{eurodata.__version__}"
        path = export_facts(con, out_dir)
        print(f"Wrote {path}")
    finally:
        con.close()
