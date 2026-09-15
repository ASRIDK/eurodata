import datetime as dt
import json
import random

import duckdb
import pandas as pd

from eurodata.api import EuroData
from eurodata.db import init_schema
from eurodata.graph.build import build_graph
from eurodata.ingest.pipeline import load_records
from eurodata.model.seed import seed_all
from eurodata.sources.base import Record

COUNTRIES = ["FRA", "DEU", "ITA", "ESP", "POL"]
YEARS = list(range(2005, 2021))  # 16 years -> 15 growth-rate points/country


def _seeded():
    con = duckdb.connect(":memory:")
    for seq in ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    init_schema(con)
    seed_all(con)
    return con


def _synthetic_records(seed: int = 42) -> list[Record]:
    """Plants a real, lagged relationship: GDP and GDP-per-capita share a
    common yearly "macro shock", with GDP-per-capita responding one year
    *after* GDP -> a growth-rate correlation that's essentially invisible
    contemporaneously but strong at a 1-year lag, plus a clean lead/lag
    direction (GDP leads). Unemployment is unrelated noise, as a negative
    control that must NOT survive FDR correction.
    """
    rng = random.Random(seed)
    shocks = {y: rng.gauss(0, 0.04) for y in YEARS}
    records = []
    for iso3 in COUNTRIES:
        level_a, level_b, level_c = 100.0, 100.0, 100.0
        prev_shock = 0.0
        for y in YEARS:
            records.append(Record(iso3, "nama_10_gdp", y, round(level_a, 6)))
            records.append(Record(iso3, "sdg_08_10", y, round(level_b, 6)))
            records.append(Record(iso3, "une_rt_a", y, round(level_c, 6)))
            shock = shocks[y]
            level_a *= 1 + shock + rng.gauss(0, 0.002)
            level_b *= 1 + prev_shock + rng.gauss(0, 0.002)
            level_c *= 1 + rng.gauss(0, 0.02)
            prev_shock = shock
    return records


def _load_synthetic(con):
    load_records(con, "World Bank", _synthetic_records(), vintage=dt.date(2021, 1, 1))


def _indicator_node(con, api_code: str) -> int:
    iid = con.execute("SELECT id FROM indicator WHERE api_code = ?", [api_code]).fetchone()[0]
    return con.execute(
        "SELECT id FROM graph_node WHERE node_type = 'indicator' AND ref_id = ?", [iid]
    ).fetchone()[0]


def test_correlates_with_edge_planted_relationship_and_direction():
    con = _seeded()
    _load_synthetic(con)
    build_graph(con)

    edge_types = {r[0] for r in con.execute("SELECT DISTINCT edge_type FROM graph_edge").fetchall()}
    assert "CORRELATES_WITH" in edge_types

    gdp, gdp_pc, unemployment = (
        _indicator_node(con, code) for code in ("nama_10_gdp", "sdg_08_10", "une_rt_a")
    )

    rows = con.execute(
        "SELECT src_node_id, dst_node_id, weight, props FROM graph_edge WHERE edge_type = 'CORRELATES_WITH'"
    ).fetchall()
    by_pair = {frozenset((src, dst)): (src, dst, weight, props) for src, dst, weight, props in rows}

    # GDP and GDP-per-capita share the planted shock, one year apart ->
    # invisible contemporaneously but should survive via the lagged test.
    key = frozenset((gdp, gdp_pc))
    assert key in by_pair
    src, dst, weight, props = by_pair[key]
    assert weight > 0.7
    payload = json.loads(props)
    assert payload["q_value"] < 0.05
    assert payload["n_countries"] == len(COUNTRIES)
    assert payload["relationship"] == "a_leads_b"
    # GDP's shock happens a year before GDP-per-capita's -> GDP must lead,
    # and the edge (src -> dst) must point from leader to follower.
    assert payload["direction"] == "a_leads_b"
    assert (src, dst) == (gdp, gdp_pc)
    assert all("granger_p_a_to_b" in c for c in payload["per_country"])

    # Unemployment is unrelated noise -> must not survive FDR correction.
    assert frozenset((gdp, unemployment)) not in by_pair
    assert frozenset((gdp_pc, unemployment)) not in by_pair


def test_correlates_with_edges_are_idempotent():
    con = _seeded()
    _load_synthetic(con)
    build_graph(con)
    first = con.execute(
        "SELECT COUNT(*) FROM graph_edge WHERE edge_type = 'CORRELATES_WITH'"
    ).fetchone()[0]
    assert first > 0

    build_graph(con)
    second = con.execute(
        "SELECT COUNT(*) FROM graph_edge WHERE edge_type = 'CORRELATES_WITH'"
    ).fetchone()[0]
    assert second == first


def test_no_correlation_edges_without_enough_data():
    # Only one country/indicator loaded (mirrors test_graph_build.py's
    # minimal fixture) -> nowhere near MIN_COUNTRIES, no edges at all.
    con = _seeded()
    load_records(con, "Eurostat", [Record("DEU", "nama_10_gdp", 2020, 100.0)],
                 vintage=dt.date(2021, 1, 1))
    build_graph(con)
    count = con.execute(
        "SELECT COUNT(*) FROM graph_edge WHERE edge_type = 'CORRELATES_WITH'"
    ).fetchone()[0]
    assert count == 0


def test_correlation_graph_api():
    con = _seeded()
    _load_synthetic(con)
    build_graph(con)
    db = EuroData.from_connection(con)

    everything = db.correlation_graph()
    assert len(everything) == 1
    row = everything.iloc[0]
    assert {"GDP", "GDP per capita"} == {row["indicator_a"], row["indicator_b"]}
    assert row["domain_a"] == "Economy" and row["domain_b"] == "Economy"
    assert row["relationship"] == "a_leads_b"
    assert row["direction"] == "a_leads_b"
    assert row["q_value"] < 0.05
    assert row["n_countries"] == len(COUNTRIES)

    focused = db.correlation_graph(indicator="GDP")
    assert len(focused) == 1

    unrelated = db.correlation_graph(indicator="Unemployment Rate")
    assert unrelated.empty


def test_granger_p_does_not_swallow_api_errors(monkeypatch):
    """Regression: a broken statsmodels call must raise, not read as "no direction".

    statsmodels 0.15 removed the deprecated ``verbose`` kwarg from
    ``grangercausalitytests``. The resulting TypeError was caught by a bare
    ``except Exception`` and returned as ``None``, which silently turned every
    edge's direction into "undetermined" on a fresh install.
    """
    import pytest
    from eurodata.graph import correlate

    def broken(*args, **kwargs):
        raise TypeError("grangercausalitytests() got an unexpected keyword argument 'verbose'")

    monkeypatch.setattr(correlate, "grangercausalitytests", broken)
    y = pd.Series([float(i % 3) for i in range(12)])
    x = pd.Series([float((i + 1) % 4) for i in range(12)])
    with pytest.raises(TypeError):
        correlate._granger_p(y, x)
