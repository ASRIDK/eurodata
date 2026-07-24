"""Web endpoints exercised against an injected in-memory database.

Unlike test_web_api.py (which needs the built data/eurodata.duckdb), these build
a small database in memory and point deps at it, so they cover the new endpoints
— revisions, country-correlations, export, ETag caching, chat rate-limit — with
no external data.
"""
import datetime as dt

import duckdb
import pytest
from fastapi.testclient import TestClient

from eurodata.api import EuroData
from eurodata.db import init_schema
from eurodata.ingest.pipeline import load_records
from eurodata.model.seed import seed_all
from eurodata.sources.base import Record
from web.backend import deps
from web.backend.main import app
from web.backend.ratelimit import RateLimiter


@pytest.fixture
def client(monkeypatch):
    con = duckdb.connect(":memory:")
    init_schema(con)
    seed_all(con)
    recs = []
    for i, year in enumerate(range(2010, 2021)):
        recs.append(Record("FRA", "nama_10_gdp", year, 100.0 + 10 * i))
        recs.append(Record("DEU", "nama_10_gdp", year, 90.0 + 8 * i))
    load_records(con, "World Bank", recs, vintage=dt.date(2026, 1, 1))
    # a revision of FRA GDP 2015 at a later vintage
    load_records(con, "World Bank", [Record("FRA", "nama_10_gdp", 2015, 999.0)],
                 vintage=dt.date(2027, 1, 1))
    handle = EuroData.from_connection(con)
    monkeypatch.setattr(deps, "_shared", handle)
    yield TestClient(app)
    con.close()


def test_revisions_endpoint(client):
    r = client.get("/api/revisions", params={"indicator": "GDP", "country": "FRA"})
    assert r.status_code == 200
    body = r.json()
    assert body["n_revised"] == 1
    assert {row["period"] for row in body["summary"]} == {"2015"}
    assert any(row["is_latest"] and row["value"] == 999.0 for row in body["rows"])


def test_revisions_summary_endpoint(client):
    rows = client.get("/api/revisions-summary").json()["rows"]
    assert any(r["indicator"] == "GDP" and r["period"] == "2015" for r in rows)


def test_country_correlations_endpoint_empty_without_graph(client):
    # No graph edges seeded -> valid country returns an empty list, not an error.
    r = client.get("/api/country-correlations", params={"country": "FRA"})
    assert r.status_code == 200
    assert r.json()["rows"] == []
    # unknown country -> 404 via the shared lookup handler
    assert client.get("/api/country-correlations",
                      params={"country": "Atlantis"}).status_code == 404


def test_correlate_endpoint_reports_basis(client):
    body = client.get("/api/correlate", params={"a": "GDP", "b": "GDP"}).json()
    assert body["basis"] == "growth"
    lv = client.get("/api/correlate",
                    params={"a": "GDP", "b": "GDP", "on": "levels"}).json()
    assert lv["basis"] == "levels"
    assert client.get("/api/correlate",
                      params={"a": "GDP", "b": "GDP", "on": "nonsense"}).status_code == 422


def test_export_csv_and_parquet(client):
    csv = client.get("/api/export", params={"view": "series", "indicator": "GDP",
                                            "country": "FRA"})
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"]
    assert "value" in csv.text.splitlines()[0]

    pq = client.get("/api/export", params={"view": "coverage", "fmt": "parquet"})
    assert pq.status_code == 200
    assert pq.content[:4] == b"PAR1"  # parquet magic

    assert client.get("/api/export", params={"view": "bogus"}).status_code == 422


def test_countries_etag_304(client):
    first = client.get("/api/countries")
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert first.headers["cache-control"].startswith("public")
    again = client.get("/api/countries", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_chat_rate_limit_429(client, monkeypatch):
    import web.backend.main as main
    monkeypatch.setattr(main, "_chat_limiter", RateLimiter(max_requests=1, window_seconds=100))
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    first = client.post("/api/chat", json=payload)   # passes limiter, 503 (no key)
    assert first.status_code == 503
    second = client.post("/api/chat", json=payload)  # limiter trips
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) >= 1


def test_propagate_endpoint_returns_rows(client):
    r = client.get("/api/propagate", params={"node": "GDP"})
    assert r.status_code == 200
    assert "rows" in r.json()


def test_propagate_endpoint_404s_on_an_unknown_node(client):
    r = client.get("/api/propagate", params={"node": "Not An Indicator"})
    assert r.status_code == 404


def test_propagate_endpoint_passes_through_tuning_parameters(client):
    r = client.get("/api/propagate", params={
        "node": "GDP", "shock": 2.0, "max_hops": 1, "edge_floor": 0.9})
    assert r.status_code == 200
    for row in r.json()["rows"]:
        assert row["hop"] == 1


def test_country_profile_endpoint(client):
    r = client.get("/api/country-profile", params={"country": "FRA"})
    assert r.status_code == 200
    body = r.json()
    assert body["iso3"] == "FRA"
    assert "headline" in body and "blocs" in body


def test_country_profile_endpoint_404s_on_unknown(client):
    r = client.get("/api/country-profile", params={"country": "Nowhere"})
    assert r.status_code == 404


@pytest.fixture
def conv_client(monkeypatch):
    """A 4-country GDP-per-capita panel where lower initial levels grow faster,
    so beta-convergence is real (n >= 3 for regression stats)."""
    import math as _math
    con = duckdb.connect(":memory:")
    init_schema(con)
    seed_all(con)
    recs = []
    for iso3, y0 in {"DEU": 80.0, "FRA": 40.0, "ITA": 20.0, "ESP": 10.0}.items():
        g = 0.10 - 0.02 * _math.log(y0)
        for year in range(2000, 2011):
            recs.append(Record(iso3, "sdg_08_10", year, y0 * _math.exp(g * (year - 2000))))
    load_records(con, "World Bank", recs, vintage=dt.date(2026, 1, 1))
    monkeypatch.setattr(deps, "_shared", EuroData.from_connection(con))
    yield TestClient(app)
    con.close()


def test_convergence_endpoint(conv_client):
    r = conv_client.get("/api/convergence", params={"indicator": "GDP per capita"})
    assert r.status_code == 200
    body = r.json()
    assert [row["iso3"] for row in body["rows"]] == ["ESP", "ITA", "FRA", "DEU"]
    assert body["beta"]["coefficient"] == pytest.approx(-2.0, abs=1e-6)
    assert body["beta"]["converging"] is True
    assert body["beta"]["t_stat"] is None or isinstance(body["beta"]["t_stat"], (int, float))
    assert body["sigma_trend"]["converging"] is True
    assert len(body["sigma"]) == 11


def test_convergence_endpoint_404s_on_unknown_indicator(conv_client):
    r = conv_client.get("/api/convergence", params={"indicator": "Not An Indicator"})
    assert r.status_code == 404


def test_health_is_liveness(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_endpoint_reports_ready(client):
    r = client.get("/api/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready" and body["rows"] > 0


def test_response_time_header_present(client):
    r = client.get("/api/countries")
    assert "X-Response-Time-ms" in r.headers


def test_metrics_endpoint_prometheus_format(client):
    client.get("/api/countries")  # generate at least one observation
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "eurodata_http_requests_total" in body
    assert "eurodata_http_request_duration_seconds_count" in body
    assert 'route="/api/countries"' in body
