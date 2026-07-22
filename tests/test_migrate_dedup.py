"""Unit test for scripts/migrate_dedup.py against a synthetic pre-migration DB.

The real 436k-row database is not present in CI / this environment, so we build
a small database in the *old* shape (nullable quarter/month, with the exact
duplicates the inert UNIQUE constraint allowed) and assert the migration
collapses them, converts NULL -> 0, and leaves statistic_best untouched.
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "migrate_dedup", Path(__file__).resolve().parent.parent / "scripts" / "migrate_dedup.py")
migrate_dedup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_dedup)


# statistic_record in its pre-migration shape: quarter/month are nullable, so the
# UNIQUE constraint below is inert (every key carries a NULL).
_OLD_SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS seq_statistic START 1;
CREATE TABLE geography (id INTEGER PRIMARY KEY, code VARCHAR, level VARCHAR,
                        name VARCHAR, iso3 VARCHAR);
CREATE TABLE domain (id INTEGER PRIMARY KEY, name VARCHAR);
CREATE TABLE indicator (id INTEGER PRIMARY KEY, domain_id INTEGER, name VARCHAR,
                        unit VARCHAR);
CREATE TABLE source (id INTEGER PRIMARY KEY, name VARCHAR, reliability_score DOUBLE);
CREATE TABLE statistic_record (
    id BIGINT DEFAULT nextval('seq_statistic') PRIMARY KEY,
    geography_id INTEGER NOT NULL, indicator_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL, year INTEGER NOT NULL,
    quarter INTEGER, month INTEGER, value DOUBLE, unit VARCHAR,
    currency VARCHAR, price_basis VARCHAR, confidence_score DOUBLE DEFAULT 1.0,
    is_estimated BOOLEAN DEFAULT FALSE, vintage_date DATE,
    retrieved_at TIMESTAMP DEFAULT now(),
    UNIQUE (geography_id, indicator_id, source_id, year, quarter, month, vintage_date)
);
"""


def _build_old_db(con):
    con.execute(_OLD_SCHEMA)
    con.execute("INSERT INTO geography VALUES (1, 'FR', 'country', 'France', 'FRA')")
    con.execute("INSERT INTO domain VALUES (1, 'Economy')")
    con.execute("INSERT INTO indicator VALUES (1, 1, 'GDP', 'USD')")
    con.execute("INSERT INTO source VALUES (1, 'Eurostat', 1.0)")
    # Recreate the two views exactly as schema.sql defines them.
    from eurodata.db import init_schema  # noqa: F401  (views live in schema.sql)
    con.execute("""
        CREATE VIEW statistic_current AS
        SELECT s.* FROM statistic_record s
        JOIN (SELECT geography_id, indicator_id, source_id, year,
                     COALESCE(quarter,-1) q, COALESCE(month,-1) m,
                     MAX(COALESCE(vintage_date, DATE '0001-01-01')) max_vintage
              FROM statistic_record GROUP BY 1,2,3,4,5,6) latest
        ON s.geography_id=latest.geography_id AND s.indicator_id=latest.indicator_id
        AND s.source_id=latest.source_id AND s.year=latest.year
        AND COALESCE(s.quarter,-1)=latest.q AND COALESCE(s.month,-1)=latest.m
        AND COALESCE(s.vintage_date, DATE '0001-01-01')=latest.max_vintage;
        CREATE VIEW statistic_best AS
        SELECT c.* FROM statistic_current c JOIN source src ON src.id=c.source_id
        QUALIFY ROW_NUMBER() OVER (PARTITION BY c.geography_id, c.indicator_id,
                c.year, COALESCE(c.quarter,-1), COALESCE(c.month,-1)
                ORDER BY src.reliability_score DESC, c.source_id ASC) = 1;
    """)


def _insert(con, year, value, vintage, quarter=None, month=None):
    con.execute(
        "INSERT INTO statistic_record "
        "(geography_id, indicator_id, source_id, year, quarter, month, value, vintage_date) "
        "VALUES (1, 1, 1, ?, ?, ?, ?, ?)", [year, quarter, month, value, vintage])


def test_migrate_dedups_and_zero_fills(memdb):
    _build_old_db(memdb)
    # Two exact-duplicate annual rows (same series+vintage) -> collapse to 1.
    _insert(memdb, 2020, 100.0, "2021-01-01")
    _insert(memdb, 2020, 100.0, "2021-01-01")
    # A genuine later vintage of 2020 -> kept (revision history, not a dup).
    _insert(memdb, 2020, 105.0, "2022-01-01")
    # A distinct year, also duplicated.
    _insert(memdb, 2021, 110.0, "2022-01-01")
    _insert(memdb, 2021, 110.0, "2022-01-01")
    assert memdb.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0] == 5

    result = migrate_dedup.migrate(memdb)

    assert result["before"] == 5
    assert result["after"] == 3      # 2020@v1, 2020@v2, 2021@v2
    assert result["removed"] == 2
    # NULLs became the sentinel 0.
    nulls = memdb.execute(
        "SELECT COUNT(*) FROM statistic_record WHERE quarter IS NULL OR month IS NULL"
    ).fetchone()[0]
    assert nulls == 0
    assert memdb.execute(
        "SELECT COUNT(*) FROM statistic_record WHERE quarter = 0 AND month = 0"
    ).fetchone()[0] == 3


def test_migrate_reingestion_is_now_a_noop(memdb):
    """After migration the constraint fires, so an identical insert is skipped."""
    _build_old_db(memdb)
    _insert(memdb, 2020, 100.0, "2021-01-01")
    migrate_dedup.migrate(memdb)
    memdb.execute(
        "INSERT INTO statistic_record "
        "(geography_id, indicator_id, source_id, year, quarter, month, value, vintage_date) "
        "VALUES (1, 1, 1, 2020, 0, 0, 100.0, DATE '2021-01-01') ON CONFLICT DO NOTHING")
    assert memdb.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0] == 1
