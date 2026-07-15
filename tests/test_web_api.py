"""REST endpoints against the real (read-only) database."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not Path("data/eurodata.duckdb").exists(),
    reason="requires the built database (scripts/init_db.py + run_ingestion.py)")

from fastapi.testclient import TestClient  # noqa: E402

from web.backend.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    lo, hi = r.json()["years"]
    assert lo >= 2000 and hi >= lo


def test_countries():
    rows = client.get("/api/countries").json()["rows"]
    assert len(rows) >= 40
    assert {"iso3", "name"} <= set(rows[0])


def test_series_filters():
    rows = client.get("/api/series", params={
        "indicator": "GDP", "country": "FRA", "start": 2010, "end": 2015,
    }).json()["rows"]
    assert rows and all(r["iso3"] == "FRA" for r in rows)
    assert all(2010 <= r["year"] <= 2015 for r in rows)
    assert {"value", "unit", "source", "is_proxy"} <= set(rows[0])


def test_unknown_indicator_404_with_suggestion():
    r = client.get("/api/series", params={"indicator": "GPD"})
    assert r.status_code == 404
    assert "GDP" in r.json()["detail"]


def test_compare_wide():
    rows = client.get("/api/compare", params={
        "countries": "FRA,DEU", "indicator": "Population",
    }).json()["rows"]
    assert rows and {"year", "FRA", "DEU"} <= set(rows[0])


def test_latest_ranked():
    rows = client.get("/api/latest", params={
        "indicator": "GDP per capita", "bloc": "EU",
    }).json()["rows"]
    assert rows
    values = [r["value"] for r in rows]
    assert values == sorted(values, reverse=True)


def test_events_filter():
    rows = client.get("/api/events", params={"since": "2020-01-01"}).json()["rows"]
    assert rows and all(str(r["start_date"]) >= "2020-01-01" for r in rows)


def test_coverage():
    rows = client.get("/api/coverage").json()["rows"]
    assert len(rows) >= 20
    assert {"indicator", "rows", "countries"} <= set(rows[0])


def test_correlate():
    rows = client.get("/api/correlate", params={
        "a": "Internet Users %", "b": "GDP per capita",
    }).json()["rows"]
    assert rows and {"iso3", "correlation", "n_years"} <= set(rows[0])


def test_correlation_graph():
    rows = client.get("/api/correlation-graph").json()["rows"]
    assert rows and {"indicator_a", "indicator_b", "weight", "relationship",
                      "direction", "q_value", "n_countries"} <= set(rows[0])
    assert all(r["q_value"] < 0.05 for r in rows)

    focused = client.get("/api/correlation-graph", params={"indicator": "GDP"}).json()["rows"]
    assert focused
    assert all("GDP" in (r["indicator_a"], r["indicator_b"]) for r in focused)


def test_indicator_trend():
    rows = client.get("/api/indicator-trend", params={
        "indicators": "GDP per capita,Internet Users %",
    }).json()["rows"]
    assert rows and {"indicator", "year", "value", "n_countries", "base_year"} <= set(rows[0])
    names = {r["indicator"] for r in rows}
    assert names == {"GDP per capita", "Internet Users %"}
    # Rebased: every indicator sits at exactly 100 in the shared base year.
    base_year = rows[0]["base_year"]
    at_base = [r["value"] for r in rows if r["year"] == base_year]
    assert len(at_base) == 2 and all(abs(v - 100.0) < 1e-9 for v in at_base)

    assert client.get("/api/indicator-trend", params={"indicators": " , "}).status_code == 422
