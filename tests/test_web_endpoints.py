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
