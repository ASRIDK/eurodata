"""Tests for the data-quality contracts (eurodata.ingest.quality).

Each contract is exercised against an in-memory database in both its passing
and failing state, so the gates are proven to actually catch the problems they
claim to.
"""
import datetime as dt

import duckdb
import pytest

from eurodata.db import init_schema
from eurodata.ingest.pipeline import load_records
from eurodata.ingest.quality import (
    DataQualityError, QualityReport, check_freshness, check_no_failed_ingestion,
    check_nuts_rollup, check_referential_integrity, check_row_count,
    check_value_finiteness, run_quality_checks,
)
from eurodata.model.seed import seed_all
from eurodata.sources.base import Record

_AS_OF = dt.date(2026, 1, 1)


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    init_schema(c)
    seed_all(c)
    yield c
    c.close()


def _load_gdp(con, first=2000, last=2024, n_countries=("FRA", "DEU", "ITA", "ESP")):
    recs = []
    for iso3 in n_countries:
        for year in range(first, last + 1):
            recs.append(Record(iso3, "nama_10_gdp", year, 1000.0 + year))
    load_records(con, "World Bank", recs, vintage=dt.date(2026, 1, 1))


def test_row_count_pass_and_fail(con):
    _load_gdp(con)
    assert check_row_count(con, minimum=10).passed
    bad = check_row_count(con, minimum=10_000_000)
    assert not bad.passed and bad.blocking


def test_referential_integrity_catches_orphan(con):
    _load_gdp(con)
    assert check_referential_integrity(con).passed
    # inject a fact pointing at a non-existent geography
    con.execute("INSERT INTO statistic_record "
                "(geography_id, indicator_id, source_id, year, value) "
                "VALUES (999999, 1, 1, 2020, 1.0)")
    orphan = check_referential_integrity(con)
    assert not orphan.passed and orphan.blocking
    assert orphan.metrics["orphan_geography"] == 1


def test_value_finiteness(con):
    _load_gdp(con)
    assert check_value_finiteness(con).passed
    con.execute("INSERT INTO statistic_record "
                "(geography_id, indicator_id, source_id, year, value) "
                "VALUES (1, 1, 1, 2020, 'inf'::DOUBLE)")
    bad = check_value_finiteness(con)
    assert not bad.passed and bad.blocking


def test_freshness_warn_and_error(con):
    # data ending 2024, as-of 2026 -> age 2 -> fresh
    _load_gdp(con, last=2024)
    assert check_freshness(con, warn_years=3, error_years=8, as_of=_AS_OF).passed

    # only old data (ends 2019) -> age 7 -> warn (non-blocking), then error
    con.execute("DELETE FROM statistic_record")
    _load_gdp(con, first=2000, last=2019)
    warn = check_freshness(con, warn_years=3, error_years=8, as_of=_AS_OF)
    assert not warn.passed and not warn.blocking and warn.severity == "warn"
    err = check_freshness(con, warn_years=3, error_years=6, as_of=_AS_OF)
    assert not err.passed and err.blocking


def test_no_failed_ingestion(con):
    _load_gdp(con)  # writes a 'completed' ingestion_run
    assert check_no_failed_ingestion(con).passed
    con.execute("INSERT INTO ingestion_run (source, started_at, ended_at, status) "
                "VALUES ('World Bank', now(), now(), 'failed')")
    bad = check_no_failed_ingestion(con)
    assert not bad.passed and bad.blocking
    assert "World Bank" in bad.metrics["failed_sources"]


def _fra_nuts2(con, k=2):
    return [r[0] for r in con.execute(
        "SELECT g.code FROM geography g JOIN geography p ON p.id = g.parent_id "
        "WHERE g.level = 'NUTS2' AND p.iso3 = 'FRA' ORDER BY g.code LIMIT ?", [k]).fetchall()]


def test_nuts_rollup_skipped_when_no_regional_data(con):
    _load_gdp(con)  # country level only
    skipped = check_nuts_rollup(con)
    assert skipped.passed and skipped.severity == "warn"
    assert skipped.metrics["n_comparisons"] == 0


def test_nuts_rollup_reconciles_and_catches_mismatch(con):
    r1, r2 = _fra_nuts2(con)
    # Population (demo_pjan, additive): country 30 = 20 + 10 across two regions
    load_records(con, "Eurostat", [
        Record("FRA", "demo_pjan", 2020, 30.0),
        Record(r1, "demo_pjan", 2020, 20.0),
        Record(r2, "demo_pjan", 2020, 10.0),
    ], vintage=dt.date(2026, 1, 1))
    ok = check_nuts_rollup(con)
    assert ok.passed and ok.metrics["n_comparisons"] == 1

    # now break it: regions sum to 40 against a country total of 30
    con.execute("UPDATE statistic_record SET value = 30.0 "
                "WHERE indicator_id = (SELECT id FROM indicator WHERE api_code='demo_pjan') "
                "AND geography_id = (SELECT id FROM geography WHERE code = ?)", [r2])
    bad = check_nuts_rollup(con, tolerance=0.02)
    assert not bad.passed and bad.blocking and bad.metrics["n_mismatched"] == 1


def test_run_quality_checks_report_and_gate(con):
    _load_gdp(con)
    report = run_quality_checks(con, min_rows=10, as_of=_AS_OF)
    assert isinstance(report, QualityReport)
    assert {c.name for c in report.checks} == {
        "row_count", "referential_integrity", "value_finiteness",
        "freshness", "ingestion_runs", "nuts_rollup"}
    assert report.ok
    report.raise_for_status()  # does not raise
    assert "Data-quality report [OK]" in report.summary()

    # a blocking failure makes the report not-ok and raises
    failing = run_quality_checks(con, min_rows=10_000_000, as_of=_AS_OF)
    assert not failing.ok
    with pytest.raises(DataQualityError):
        failing.raise_for_status()
