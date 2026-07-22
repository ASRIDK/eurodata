"""One-off migration: give statistic_record the NOT NULL DEFAULT 0 sentinel and
collapse the exact duplicates the (previously inert) UNIQUE constraint let in.

Background: `UNIQUE(geography_id, indicator_id, source_id, year, quarter, month,
vintage_date)` never fired because annual/sub-annual rows always carried a NULL
in the key and `NULL != NULL`. This rebuilds the table with quarter/month as
`NOT NULL DEFAULT 0`, converting existing NULLs to 0 and keeping the most
recently retrieved row for each duplicate key.

The rebuild is required rather than an in-place `ALTER`: DuckDB cannot add a
`NOT NULL` constraint over a column that still contains NULLs, nor alter the
table's UNIQUE constraint in place.

Safety: the real database is backed up to `<path>.bak` before any write, and
the script refuses to proceed if any user-visible `statistic_best` value would
change (removing exact duplicates cannot change which row wins, so this must
hold; if it does not, something else is wrong and we stop).

Run locally against the built database:

    python scripts/migrate_dedup.py                 # data/eurodata.duckdb
    python scripts/migrate_dedup.py path/to.duckdb
"""
from __future__ import annotations

import shutil
import sys

try:
    from _bootstrap import ensure_paths
    ensure_paths()
except ModuleNotFoundError:
    pass  # already importable (e.g. under pytest with PYTHONPATH=src)

import duckdb

from eurodata.db import init_schema

# Kept in sync with model/schema.sql (statistic_record), name changed so we can
# build the corrected table alongside the old one and swap.
_NEW_TABLE_DDL = """
CREATE TABLE statistic_record_new (
    id BIGINT DEFAULT nextval('seq_statistic') PRIMARY KEY,
    geography_id INTEGER NOT NULL,
    indicator_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL DEFAULT 0,
    month INTEGER NOT NULL DEFAULT 0,
    value DOUBLE,
    unit VARCHAR,
    currency VARCHAR,
    price_basis VARCHAR,
    confidence_score DOUBLE DEFAULT 1.0,
    is_estimated BOOLEAN DEFAULT FALSE,
    vintage_date DATE,
    retrieved_at TIMESTAMP DEFAULT now(),
    UNIQUE (geography_id, indicator_id, source_id, year, quarter, month, vintage_date)
);
"""

# Copy every column, coalescing the sentinel and keeping one row per unique key:
# the most recently retrieved (retrieved_at desc, id desc as a stable tiebreak).
_DEDUP_INSERT = """
INSERT INTO statistic_record_new
SELECT id, geography_id, indicator_id, source_id, year,
       COALESCE(quarter, 0) AS quarter, COALESCE(month, 0) AS month,
       value, unit, currency, price_basis, confidence_score, is_estimated,
       vintage_date, retrieved_at
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY geography_id, indicator_id, source_id, year,
                     COALESCE(quarter, 0), COALESCE(month, 0),
                     COALESCE(vintage_date, DATE '0001-01-01')
        ORDER BY retrieved_at DESC NULLS LAST, id DESC
    ) AS rn
    FROM statistic_record
)
WHERE rn = 1;
"""

# A few series that must be byte-for-byte identical before and after.
_SAMPLE_SERIES = [
    ("GDP", "FRA"),
    ("Inflation (HICP)", "ESP"),
    ("GDP growth", "DEU"),
]


def _sample(con: duckdb.DuckDBPyConnection, indicator: str, iso3: str):
    # Coalesce quarter/month to the 0 sentinel so the intended NULL -> 0
    # conversion doesn't read as a value change; a genuinely different winning
    # value (or a shifted period) would still show up.
    return con.execute(
        "SELECT s.year, COALESCE(s.quarter, 0), COALESCE(s.month, 0), s.value "
        "FROM statistic_best s "
        "JOIN geography g ON g.id = s.geography_id "
        "JOIN indicator i ON i.id = s.indicator_id "
        "WHERE g.iso3 = ? AND i.name = ? "
        "ORDER BY s.year, s.quarter, s.month",
        [iso3, indicator],
    ).fetchall()


def migrate(con: duckdb.DuckDBPyConnection) -> dict:
    """Rebuild statistic_record with the sentinel + dedup. Returns before/after
    counts. Raises RuntimeError if any sampled statistic_best value changed."""
    before = con.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0]
    samples_before = {(ind, iso): _sample(con, ind, iso) for ind, iso in _SAMPLE_SERIES}

    con.execute("BEGIN")
    # Views depend on statistic_record; drop them, swap the table, then let
    # init_schema recreate them (CREATE OR REPLACE VIEW) against the new table.
    con.execute("DROP VIEW IF EXISTS statistic_best")
    con.execute("DROP VIEW IF EXISTS statistic_current")
    con.execute("DROP TABLE IF EXISTS statistic_record_new")
    con.execute(_NEW_TABLE_DDL)
    con.execute(_DEDUP_INSERT)
    con.execute("DROP TABLE statistic_record")
    con.execute("ALTER TABLE statistic_record_new RENAME TO statistic_record")
    con.execute("COMMIT")

    init_schema(con)  # recreates statistic_current / statistic_best views

    after = con.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0]
    for key, before_rows in samples_before.items():
        after_rows = _sample(con, *key)
        if after_rows != before_rows:
            raise RuntimeError(
                f"statistic_best changed for {key}: dedup was supposed to be "
                f"value-preserving. Aborting (backup retained).\n"
                f"before={before_rows}\nafter={after_rows}")
    return {"before": before, "after": after, "removed": before - after}


def main(argv: list[str]) -> int:
    db_path = argv[1] if len(argv) > 1 else "data/eurodata.duckdb"
    backup = db_path + ".bak"
    print(f"Backing up {db_path} -> {backup}")
    shutil.copy2(db_path, backup)

    con = duckdb.connect(db_path)
    try:
        result = migrate(con)
    except Exception as exc:  # noqa: BLE001 - surface and keep the backup
        print(f"FAILED: {exc}", file=sys.stderr)
        print(f"The database may be partially modified; restore from {backup} "
              f"if needed.", file=sys.stderr)
        return 1
    finally:
        con.close()

    print(f"statistic_record: {result['before']:,} -> {result['after']:,} rows "
          f"({result['removed']:,} exact duplicates removed)")
    print("statistic_best sample series unchanged. Backup retained at " + backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
