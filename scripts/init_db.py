"""Create the DuckDB database and seed reference data."""
from _bootstrap import ensure_paths

ensure_paths()

from eurodata.db import connect
from eurodata.model.seed import seed_all

if __name__ == "__main__":
    con = connect()
    try:
        seed_all(con)
        n = con.execute("SELECT COUNT(*) FROM geography").fetchone()[0]
        print(f"Initialized DB with {n} countries.")
    finally:
        con.close()
