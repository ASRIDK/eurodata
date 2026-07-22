"""eurodata web API — FastAPI wrapper over the public Python API.

Run from the repo root:
    PYTHONPATH=src:. .venv/bin/uvicorn web.backend.main:app --port 8000

The database is opened read-only (see deps.py); this process never writes.
"""
from __future__ import annotations

import hashlib
import io
from typing import Any, Literal

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

load_dotenv()  # GOOGLE_API_KEY etc. from .env, regardless of how uvicorn was launched
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from eurodata import EuroDataLookupError
from web.backend import deps
from web.backend.chat import ChatNotConfiguredError, run_chat
from web.backend.ratelimit import from_env as _rate_limiter_from_env
from web.backend.tools import _clean, df_records

app = FastAPI(title="eurodata API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "Retry-After", "Content-Disposition"],
)

_chat_limiter = _rate_limiter_from_env()


@app.exception_handler(EuroDataLookupError)
def _lookup_error(_: Request, exc: EuroDataLookupError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def _query(method: str, /, **kwargs) -> Any:
    """Run one EuroData method on a fresh per-request cursor (see deps.py)."""
    return getattr(deps.get_ed(), method)(**kwargs)


def _latest_vintage() -> str:
    """Max vintage date in the dataset; the cache key for static-ish endpoints."""
    row = deps.get_ed().query(
        "SELECT CAST(MAX(vintage_date) AS VARCHAR) AS v FROM statistic_record")
    return (row["v"].iloc[0] if not row.empty and row["v"].iloc[0] else "0")


def _cached(request: Request, name: str, build) -> Response:
    """Serve a static-ish payload with an ETag/Cache-Control keyed on the latest
    vintage. Returns 304 when the client's If-None-Match still matches."""
    etag = 'W/"' + hashlib.sha256(f"{name}:{_latest_vintage()}".encode()).hexdigest()[:16] + '"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=300"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=build(), headers=headers)


@app.get("/api/health")
def health() -> dict:
    lo, hi = _query("years")
    return {"status": "ok", "years": [lo, hi]}


@app.get("/api/countries")
def countries(request: Request) -> Response:
    return _cached(request, "countries",
                   lambda: {"rows": df_records(_query("countries"))})


@app.get("/api/regions")
def regions(country: str | None = None) -> dict:
    return {"rows": df_records(_query("regions", country=country))}


@app.get("/api/blocs")
def blocs() -> dict:
    return {"rows": df_records(_query("blocs"))}


@app.get("/api/domains")
def domains() -> dict:
    return {"rows": df_records(_query("domains"))}


@app.get("/api/indicators")
def indicators(request: Request, domain: str | None = None) -> Response:
    return _cached(request, f"indicators:{domain or ''}",
                   lambda: {"rows": df_records(_query("indicators", domain=domain))})


@app.get("/api/sources")
def sources() -> dict:
    return {"rows": df_records(_query("sources"))}


@app.get("/api/correlation-graph")
def correlation_graph(indicator: str | None = None) -> dict:
    return {"rows": df_records(_query("correlation_graph", indicator=indicator))}


@app.get("/api/indicator-trend")
def indicator_trend(indicators: str, start: int | None = None,
                    end: int | None = None) -> dict:
    names = [s.strip() for s in indicators.split(",") if s.strip()]
    if not names:
        raise HTTPException(422, "indicators must be a comma-separated list")
    df = _query("indicator_trends", indicators=names, start=start, end=end)
    return {"rows": df_records(df)}


@app.get("/api/search")
def search(q: str) -> dict:
    return {"rows": df_records(_query("search_indicators", text=q))}


@app.get("/api/coverage")
def coverage() -> dict:
    return {"rows": df_records(_query("coverage"))}


@app.get("/api/series")
def series(indicator: str | None = None, country: str | None = None,
           bloc: str | None = None, domain: str | None = None,
           start: int | None = None, end: int | None = None,
           rebase: int | None = None, yoy: bool = False,
           limit: int = 5000) -> dict:
    if rebase is not None and yoy:
        raise HTTPException(422, "rebase and yoy are mutually exclusive")
    df = _query("series", indicator=indicator, country=country, bloc=bloc,
                domain=domain, start=start, end=end, rebase=rebase, yoy=yoy)
    return {"rows": df_records(df, limit)}


@app.get("/api/forecast")
def forecast(indicator: str, country: str, horizon: int = 5,
             level: float = 0.8) -> dict:
    if not 1 <= horizon <= 30:
        raise HTTPException(422, "horizon must be between 1 and 30")
    if not 0 < level < 1:
        raise HTTPException(422, "level must be between 0 and 1 (exclusive)")
    df = _query("forecast", indicator=indicator, country=country,
                horizon=horizon, level=level)
    hist = df[df["kind"] == "history"]
    fc = df[df["kind"] == "forecast"]
    return {
        "history": df_records(hist[["t", "period", "value"]]),
        "forecast": df_records(fc[["t", "period", "value", "lo", "hi"]]),
        "method": _clean(df.attrs["method"]),
        "freq": _clean(df.attrs["freq"]),
        "backtest_mae": _clean(df.attrs["backtest_mae"]),
        "fallback": _clean(df.attrs["fallback"]),
        "disclaimer": _clean(df.attrs["disclaimer"]),
        "unit": _clean(df.attrs["unit"]),
    }


@app.get("/api/compare")
def compare(countries: str, indicator: str,
            start: int | None = None, end: int | None = None) -> dict:
    iso_list = [c.strip() for c in countries.split(",") if c.strip()]
    if not iso_list:
        raise HTTPException(422, "countries must be a comma-separated list")
    df = _query("compare", countries=iso_list, indicator=indicator,
                start=start, end=end)
    if df.empty:
        return {"rows": []}
    return {"rows": df_records(df.reset_index())}


@app.get("/api/latest")
def latest(indicator: str, bloc: str | None = None) -> dict:
    return {"rows": df_records(_query("latest", indicator=indicator, bloc=bloc))}


@app.get("/api/provenance")
def provenance(indicator: str, country: str) -> dict:
    return {"rows": df_records(_query("provenance", indicator=indicator, country=country))}


@app.get("/api/country-blocs")
def country_blocs(country: str) -> dict:
    return {"rows": df_records(_query("country_blocs", country=country))}


@app.get("/api/country-indicators")
def country_indicators(country: str) -> dict:
    return {"rows": df_records(_query("country_indicators", country=country))}


@app.get("/api/events")
def events(country: str | None = None, event_type: str | None = None,
           bloc: str | None = None, since: str | None = None,
           until: str | None = None) -> dict:
    df = _query("events", country=country, event_type=event_type, bloc=bloc,
                since=since, until=until)
    return {"rows": df_records(df)}


@app.get("/api/event-types")
def event_types() -> dict:
    return {"rows": df_records(_query("event_types"))}


@app.get("/api/event-study")
def event_study(indicator: str, event_code: str | None = None,
                event_type: str | None = None, window_years: int = 3) -> dict:
    df = _query("event_study", indicator=indicator, event_code=event_code,
                event_type=event_type, window_years=window_years)
    return {"rows": df_records(df)}


@app.get("/api/correlate")
def correlate(a: str, b: str, lag: int = 0, min_years: int = 10,
              on: str = "growth") -> dict:
    if on not in ("growth", "levels"):
        raise HTTPException(422, "on must be 'growth' or 'levels'")
    df = _query("lagged_correlation", indicator_a=a, indicator_b=b, lag=lag,
                min_years=min_years, on=on)
    return {"rows": df_records(df), "basis": on}


@app.get("/api/revisions")
def revisions(indicator: str, country: str) -> dict:
    df = _query("revisions", indicator=indicator, country=country)
    return {
        "rows": df_records(df),
        "summary": df_records(df.attrs.get("summary")),
        "n_revised": int(df.attrs.get("n_revised", 0)),
    }


@app.get("/api/revisions-summary")
def revisions_summary(country: str | None = None, indicator: str | None = None) -> dict:
    df = _query("revisions_summary", country=country, indicator=indicator)
    return {"rows": df_records(df)}


@app.get("/api/country-correlations")
def country_correlations(country: str, limit: int = 20) -> dict:
    df = _query("country_correlations", country=country, limit=limit)
    return {"rows": df_records(df)}


_EXPORT_VIEWS = {"series", "latest", "compare", "coverage", "revisions-summary"}


@app.get("/api/export")
def export(view: str, fmt: str = "csv", indicator: str | None = None,
           country: str | None = None, countries: str | None = None,
           bloc: str | None = None, start: int | None = None,
           end: int | None = None) -> Response:
    """Download any series/ranking view as CSV or Parquet. DuckDB-backed."""
    if view not in _EXPORT_VIEWS:
        raise HTTPException(422, f"view must be one of {sorted(_EXPORT_VIEWS)}")
    if fmt not in ("csv", "parquet"):
        raise HTTPException(422, "fmt must be 'csv' or 'parquet'")
    if view == "series":
        df = _query("series", indicator=indicator, country=country, bloc=bloc,
                    start=start, end=end)
    elif view == "latest":
        if not indicator:
            raise HTTPException(422, "latest export needs an indicator")
        df = _query("latest", indicator=indicator, bloc=bloc)
    elif view == "compare":
        iso_list = [c.strip() for c in (countries or "").split(",") if c.strip()]
        if not iso_list or not indicator:
            raise HTTPException(422, "compare export needs indicator and countries")
        df = _query("compare", countries=iso_list, indicator=indicator,
                    start=start, end=end).reset_index()
    elif view == "coverage":
        df = _query("coverage")
    else:  # revisions-summary
        df = _query("revisions_summary", country=country, indicator=indicator)

    stem = f"eurodata-{view}"
    if indicator:
        stem += "-" + indicator.lower().replace(" ", "_")[:40]
    if fmt == "parquet":
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return Response(
            content=buf.getvalue(), media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{stem}.parquet"'})
    csv = df.to_csv(index=False)
    return Response(
        content=csv, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request) -> dict:
    if not req.messages or req.messages[-1].role != "user":
        raise HTTPException(422, "last message must be from the user")
    client_ip = request.client.host if request.client else "unknown"
    retry_after = _chat_limiter.check(client_ip)
    if retry_after is not None:
        raise HTTPException(
            429, "Rate limit exceeded for the AI analyst. Please wait and retry.",
            headers={"Retry-After": str(int(retry_after))})
    try:
        blocks = run_chat([m.model_dump() for m in req.messages])
    except ChatNotConfiguredError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # provider/tool failure → clean frontend error
        raise HTTPException(502, f"AI analyst failed: {exc}") from exc
    return {"role": "assistant", "blocks": blocks}
