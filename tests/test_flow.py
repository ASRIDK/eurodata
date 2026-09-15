"""Smoke test for the Prefect ingestion flow, run fully offline.

Prefect state is isolated to a temp PREFECT_HOME and the network sources are
replaced with an empty list, so the test exercises the real orchestration —
graph build, quality gate, gating behaviour — without any external calls.
"""
import datetime as dt
import os
import sys
import tempfile

# Isolate Prefect's local state before it is imported.
os.environ.setdefault("PREFECT_HOME", tempfile.mkdtemp(prefix="prefect-test-"))
os.environ.setdefault("PREFECT_LOGGING_LEVEL", "WARNING")

import duckdb  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("prefect")

from eurodata.db import connect, init_schema  # noqa: E402
from eurodata.ingest.pipeline import load_records  # noqa: E402
from eurodata.ingest.quality import DataQualityError  # noqa: E402
from eurodata.model.seed import seed_all  # noqa: E402
from eurodata.sources.base import Record  # noqa: E402
from flows import ingestion as flow_mod  # noqa: E402


def _seed_db(path: str) -> None:
    con = connect(path)
    try:
        init_schema(con)
        seed_all(con)
        recs = []
        for iso3 in ("FRA", "DEU", "ITA", "ESP"):
            for year in range(2000, 2025):
                recs.append(Record(iso3, "nama_10_gdp", year, 1000.0 + year))
                recs.append(Record(iso3, "une_rt_a", year, 5.0 + (year % 5)))
                recs.append(Record(iso3, "demo_pjan", year, 50.0 + year % 7))
        load_records(con, "World Bank", recs, vintage=dt.date(2026, 1, 1))
    finally:
        con.close()


def test_ingestion_flow_offline(tmp_path, monkeypatch):
    db_path = str(tmp_path / "flow.duckdb")
    _seed_db(db_path)
    # no network: the flow ingests an empty set of sources, then builds the
    # graph and runs the quality gate over the pre-seeded data.
    monkeypatch.setattr(flow_mod, "all_sources", lambda: [])

    report = flow_mod.ingestion_flow(db_path=db_path, do_release=False, min_rows=10)

    assert report["ok"] is True
    names = {c["name"] for c in report["checks"]}
    assert "nuts_rollup" in names and "freshness" in names
    # the graph task actually wrote nodes
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM graph_node").fetchone()[0] > 0
    finally:
        con.close()


def test_quality_gate_blocks_the_flow(tmp_path, monkeypatch):
    db_path = str(tmp_path / "flow2.duckdb")
    _seed_db(db_path)
    monkeypatch.setattr(flow_mod, "all_sources", lambda: [])
    # an impossibly high row floor makes the row_count contract fail -> the gate
    # raises -> the flow fails.
    with pytest.raises(DataQualityError):
        flow_mod.ingestion_flow(db_path=db_path, do_release=False, min_rows=10_000_000)


def test_flow_ingests_every_registered_source(tmp_path, monkeypatch):
    """Regression: the flow must see the source registry populated.

    ``all_sources()`` reads a registry that is only filled when the source
    modules are imported. The flow used to import them inside the per-source
    task only, so at flow level the registry was empty, zero ingest tasks ran,
    and the row-count gate then failed every scheduled CI refresh.
    """
    db_path = str(tmp_path / "flow3.duckdb")
    _seed_db(db_path)
    # Start from an empty registry, as a fresh CI process does: forget any
    # source module another test already imported so re-importing re-registers.
    from eurodata.sources import registry
    for name in flow_mod._SOURCE_MODULES:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(registry, "_REGISTRY", {})
    monkeypatch.setattr(flow_mod, "all_sources", registry.all_sources)
    # No network: stub the fetch+load step and record which sources were run.
    seen: list[str] = []
    def fake_run_source(con, source_name, start_year):
        seen.append(source_name)
        return 0
    monkeypatch.setattr(flow_mod, "run_source", fake_run_source)

    flow_mod.ingestion_flow(db_path=db_path, do_release=False, min_rows=10)

    assert sorted(seen) == ["ECB", "Eurostat", "OECD", "World Bank"]
