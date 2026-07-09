"""Ingestion failures must be visible, never silently swallowed."""
import duckdb

from eurodata.db import init_schema
from eurodata.ingest.pipeline import run_source
from eurodata.model.seed import seed_all
from eurodata.sources.base import BaseFetcher, Record
from eurodata.sources.registry import register


def _fresh_db():
    con = duckdb.connect(":memory:")
    init_schema(con)
    seed_all(con)
    return con


def test_disabled_source_records_skip_with_reason():
    @register
    class DisabledDummy(BaseFetcher):
        source_name = "ECB"  # reuse a seeded source name
        enabled = False
        disabled_reason = "not wired"

        def fetch(self, start_year):
            raise AssertionError("must not be called")

    con = _fresh_db()
    assert run_source(con, "ECB", 2000) == 0
    status, error = con.execute(
        "SELECT status, error FROM ingestion_run").fetchone()
    assert status == "skipped" and error == "not wired"


def test_per_series_errors_are_persisted():
    @register
    class Flaky(BaseFetcher):
        source_name = "World Bank"  # reuse a seeded source name

        def fetch(self, start_year):
            self.errors.append(("SERIES.X", "boom"))
            return [Record("DEU", "nama_10_gdp", 2020, 1.0)]

    con = _fresh_db()
    assert run_source(con, "World Bank", 2000) == 1
    assert con.execute("SELECT source, series, error FROM ingestion_error").fetchall() == [
        ("World Bank", "SERIES.X", "boom")]
    assert con.execute("SELECT status FROM ingestion_run").fetchone()[0] == \
        "completed_with_errors"


def test_total_fetch_failure_recorded_as_failed():
    @register
    class Broken(BaseFetcher):
        source_name = "OECD"  # reuse a seeded source name
        enabled = True

        def fetch(self, start_year):
            raise RuntimeError("network down")

    con = _fresh_db()
    assert run_source(con, "OECD", 2000) == 0
    status, error = con.execute(
        "SELECT status, error FROM ingestion_run").fetchone()
    assert status == "failed" and "network down" in error
