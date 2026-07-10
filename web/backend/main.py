"""eurodata web API — FastAPI wrapper over the public Python API.

Run from the repo root:
    PYTHONPATH=src:. .venv/bin/uvicorn web.backend.main:app --port 8000

The database is opened read-only (see deps.py); this process never writes.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from eurodata import EuroDataLookupError
from web.backend import deps
from web.backend.chat import ChatNotConfiguredError, run_chat
from web.backend.tools import df_records

app = FastAPI(title="eurodata API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(EuroDataLookupError)
def _lookup_error(_: Request, exc: EuroDataLookupError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def _query(method: str, /, **kwargs) -> Any:
    """Run one EuroData method under the connection lock."""
    with deps.lock:
        return getattr(deps.get_ed(), method)(**kwargs)


@app.get("/api/health")
def health() -> dict:
    lo, hi = _query("years")
    return {"status": "ok", "years": [lo, hi]}


@app.get("/api/countries")
def countries() -> dict:
    return {"rows": df_records(_query("countries"))}


@app.get("/api/blocs")
def blocs() -> dict:
    return {"rows": df_records(_query("blocs"))}


@app.get("/api/domains")
def domains() -> dict:
    return {"rows": df_records(_query("domains"))}


@app.get("/api/indicators")
def indicators(domain: str | None = None) -> dict:
    return {"rows": df_records(_query("indicators", domain=domain))}


@app.get("/api/sources")
def sources() -> dict:
    return {"rows": df_records(_query("sources"))}


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
           limit: int = 5000) -> dict:
    df = _query("series", indicator=indicator, country=country, bloc=bloc,
                domain=domain, start=start, end=end)
    return {"rows": df_records(df, limit)}


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
def correlate(a: str, b: str, lag: int = 0) -> dict:
    df = _query("lagged_correlation", indicator_a=a, indicator_b=b, lag=lag)
    return {"rows": df_records(df)}


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    if not req.messages or req.messages[-1].role != "user":
        raise HTTPException(422, "last message must be from the user")
    try:
        blocks = run_chat([m.model_dump() for m in req.messages])
    except ChatNotConfiguredError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # provider/tool failure → clean frontend error
        raise HTTPException(502, f"AI analyst failed: {exc}") from exc
    return {"role": "assistant", "blocks": blocks}
