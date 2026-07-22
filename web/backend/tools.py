"""Tool layer for the /api/chat AI analyst.

Every tool is a thin, read-only wrapper over the public ``eurodata`` API.
``execute_tool`` returns a :class:`ToolOutcome`: a JSON-safe payload for the
model plus the pre-built chart/table/provenance pieces the block assembler
(chat.py) uses, so the frontend never has to re-derive them.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from eurodata import EuroData, EuroDataLookupError

MAX_TABLE_ROWS = 50
MAX_MODEL_ROWS = 60
MAX_CHART_POINTS = 600


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (datetime.date, datetime.datetime, pd.Timestamp)):
        return str(value)[:10]
    if hasattr(value, "item"):  # numpy scalars
        return value.item()
    return value


def df_records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    if limit is not None:
        df = df.head(limit)
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def df_table(df: pd.DataFrame, limit: int = MAX_TABLE_ROWS) -> dict[str, Any]:
    records = df_records(df, limit)
    columns = list(df.columns)
    return {"columns": columns, "rows": [[r.get(c) for c in columns] for r in records]}


@dataclass
class ToolOutcome:
    payload: dict[str, Any]                 # what the model sees
    chart: dict[str, Any] | None = None     # {"kind", "unit", "series": [...]}
    table: dict[str, Any] | None = None     # {"columns", "rows"}
    indicators: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "search_indicators",
        "description": "Search the indicator catalog by free text (name, definition, domain, or API code). Use this first when unsure of an indicator's exact name.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Search text, e.g. 'inflation' or 'AI'"}},
            "required": ["text"],
        },
    },
    {
        "name": "get_series",
        "description": "Fetch a time series for one indicator, optionally filtered by country (ISO-3, ISO-2 or name) or bloc (EU, EZ, SCH, EFTA, EEA, NATO) and year range. Some indicators are monthly or quarterly (see the period field). Optional transforms: rebase (index=100 at a year) or yoy (% change vs same period previous year).",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "country": {"type": "string"},
                "bloc": {"type": "string"},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
                "rebase": {"type": "integer", "description": "Index each country to 100 at this year, for cross-country level comparisons"},
                "yoy": {"type": "boolean", "description": "Convert to % change vs the same period one year earlier"},
            },
            "required": ["indicator"],
        },
    },
    {
        "name": "compare_countries",
        "description": "Fetch one indicator's time series for several countries at once, for comparison charts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "countries": {"type": "array", "items": {"type": "string"}, "description": "2-8 countries (ISO-3 or names)"},
                "indicator": {"type": "string"},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
            },
            "required": ["countries", "indicator"],
        },
    },
    {
        "name": "latest",
        "description": "Most recent value of an indicator for every country (a ranking), optionally restricted to a bloc.",
        "input_schema": {
            "type": "object",
            "properties": {"indicator": {"type": "string"}, "bloc": {"type": "string"}},
            "required": ["indicator"],
        },
    },
    {
        "name": "coverage",
        "description": "Data coverage per indicator: row count, countries, first/last year. Use to answer 'what data do you have?'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_events",
        "description": "Curated European events (crises, memberships, policy milestones) with dates and primary-source URLs. Filter by country, event_type, or date range (ISO dates).",
        "input_schema": {
            "type": "object",
            "properties": {
                "country": {"type": "string"},
                "event_type": {"type": "string"},
                "since": {"type": "string"},
                "until": {"type": "string"},
            },
        },
    },
    {
        "name": "event_study",
        "description": "Before/after comparison of an indicator around an event: mean over the window before vs after, per affected country. Descriptive, not causal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "event_code": {"type": "string", "description": "Exact event code from list_events"},
                "event_type": {"type": "string", "description": "Alternative: all events of a type"},
                "window_years": {"type": "integer", "default": 3},
            },
            "required": ["indicator"],
        },
    },
    {
        "name": "render_chart",
        "description": "Render a chart of a specific kind for the user (line, bar, area, scatter, or pie). Use when the user asks for a particular chart/diagram/graph type or a custom visualisation. Build the points from data returned by the other tools — never invent values. This chart replaces the auto-generated one in the UI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["line", "bar", "area", "scatter", "pie"]},
                "title": {"type": "string", "description": "Short chart title"},
                "unit": {"type": "string", "description": "Unit of the y values"},
                "series": {
                    "type": "array",
                    "description": "One entry per line/group; pie uses only the first series (x = slice label, y = value)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "points": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "x": {"anyOf": [{"type": "string"}, {"type": "number"}], "description": "Category label, year, period, or numeric x"},
                                        "y": {"type": "number"},
                                    },
                                    "required": ["x", "y"],
                                },
                            },
                        },
                        "required": ["name", "points"],
                    },
                },
            },
            "required": ["kind", "series"],
        },
    },
    {
        "name": "correlate",
        "description": "Per-country Pearson correlation between two indicators, on year-over-year GROWTH RATES by default (so two series that both merely trend upward do NOT read as correlated). Optionally with indicator_a leading by `lag` years. Pass on='levels' only if you specifically want raw-level correlation (which is inflated by shared trends). State that you are quoting growth-rate correlation, and that correlation is not causation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator_a": {"type": "string"},
                "indicator_b": {"type": "string"},
                "lag": {"type": "integer", "default": 0},
                "on": {"type": "string", "enum": ["growth", "levels"], "default": "growth",
                       "description": "'growth' (default) correlates YoY growth rates; 'levels' correlates raw levels (trend-inflated)."},
            },
            "required": ["indicator_a", "indicator_b"],
        },
    },
    {
        "name": "forecast",
        "description": "Project one indicator's series for a single country a few periods into the future, with an uncertainty band. Uses simple auto-selected statistical models (trend/exponential-smoothing; seasonal for monthly/quarterly). This is trend extrapolation, NOT a prediction — always relay the returned disclaimer and name the method. Do not forecast further than a few years.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "country": {"type": "string", "description": "ISO-3, ISO-2, or name"},
                "horizon": {"type": "integer", "default": 5, "description": "periods ahead (1-15)"},
            },
            "required": ["indicator", "country"],
        },
    },
]


def _long_chart(rows: list[dict], *, unit: str | None) -> dict[str, Any] | None:
    """Line chart from long-format series rows (iso3/country/period/value)."""
    if not rows:
        return None
    series: dict[str, list[dict]] = {}
    for r in rows[:MAX_CHART_POINTS]:
        name = r.get("country") or r.get("iso3") or "value"
        series.setdefault(name, []).append(
            {"x": r.get("period") or r["year"], "y": r["value"]})
    return {
        "kind": "line",
        "unit": unit,
        "series": [{"name": k, "points": v} for k, v in series.items()],
    }


def _series_outcome(df: pd.DataFrame) -> ToolOutcome:
    rows = df_records(df)
    unit = rows[0]["unit"] if rows else None
    indicators = sorted({r["indicator"] for r in rows})
    sources = sorted({r["source"] for r in rows})
    warnings = sorted({
        f"{r['indicator']} is a proxy series: {r['proxy_note']}"
        for r in rows if r.get("is_proxy") and r.get("proxy_note")
    })
    payload_rows = [
        {k: r.get(k) for k in ("iso3", "period", "value")} for r in rows[:MAX_MODEL_ROWS]
    ]
    payload = {
        "unit": unit,
        "indicator": indicators,
        "sources": sources,
        "n_rows": len(rows),
        "rows_sample": payload_rows,
    }
    return ToolOutcome(
        payload=payload,
        chart=_long_chart(rows, unit=unit),
        table=df_table(df),
        indicators=indicators,
        sources=sources,
        warnings=warnings,
    )


def _render_chart_outcome(args: dict[str, Any]) -> ToolOutcome:
    """Model-authored chart: sanitise the spec and hand it to the frontend."""
    kind = args.get("kind")
    if kind not in ("line", "bar", "area", "scatter", "pie"):
        return ToolOutcome(payload={"error": f"Unknown chart kind: {kind!r}"})

    budget = MAX_CHART_POINTS
    series = []
    for s in args.get("series") or []:
        points = []
        for p in (s.get("points") or [])[:budget]:
            x, y = _clean(p.get("x")), _clean(p.get("y"))
            if x is None:
                continue
            if not isinstance(y, (int, float)):
                y = None
            if y is None and kind in ("scatter", "pie"):
                continue
            if kind == "scatter":
                try:
                    x = float(x)
                except (TypeError, ValueError):
                    continue
            points.append({"x": x, "y": y})
        if points:
            budget -= len(points)
            series.append({"name": str(s.get("name") or "value"), "points": points})
    if kind == "pie":
        series = series[:1]
    if not series:
        return ToolOutcome(payload={"error": "render_chart got no usable points"})

    chart = {"kind": kind, "unit": args.get("unit"), "series": series}
    if args.get("title"):
        chart["title"] = str(args["title"])
    return ToolOutcome(
        payload={"rendered": kind,
                 "n_series": len(series),
                 "n_points": sum(len(s["points"]) for s in series)},
        chart=chart,
    )


def execute_tool(ed: EuroData, name: str, args: dict[str, Any]) -> ToolOutcome:
    try:
        return _dispatch(ed, name, args)
    except EuroDataLookupError as exc:
        return ToolOutcome(payload={"error": str(exc)})
    except Exception as exc:  # tool must never crash the chat loop
        return ToolOutcome(
            payload={"error": f"{type(exc).__name__}: {exc}"},
            warnings=[f"Tool {name} failed: {exc}"],
        )


def _dispatch(ed: EuroData, name: str, args: dict[str, Any]) -> ToolOutcome:
    if name == "search_indicators":
        df = ed.search_indicators(args["text"])
        return ToolOutcome(payload={"indicators": df_records(df, 25)})

    if name == "get_series":
        df = ed.series(
            country=args.get("country"), indicator=args["indicator"],
            bloc=args.get("bloc"), start=args.get("start"), end=args.get("end"),
            rebase=args.get("rebase"), yoy=bool(args.get("yoy", False)))
        return _series_outcome(df)

    if name == "compare_countries":
        frames = [
            ed.series(country=c, indicator=args["indicator"],
                      start=args.get("start"), end=args.get("end"))
            for c in args["countries"][:8]
        ]
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return _series_outcome(df)

    if name == "latest":
        df = ed.latest(args["indicator"], bloc=args.get("bloc"))
        rows = df_records(df)
        unit = rows[0]["unit"] if rows else None
        top = rows[:20]
        chart = {
            "kind": "bar",
            "unit": unit,
            "series": [{
                "name": args["indicator"],
                "points": [{"x": r["iso3"], "y": r["value"]} for r in top],
            }],
        } if top else None
        outcome = _series_outcome(df)
        outcome.chart = chart
        outcome.payload["rows_sample"] = [
            {k: r[k] for k in ("iso3", "year", "value")} for r in top
        ]
        return outcome

    if name == "coverage":
        df = ed.coverage()
        return ToolOutcome(payload={"coverage": df_records(df)}, table=df_table(df))

    if name == "list_events":
        df = ed.events(
            country=args.get("country"), event_type=args.get("event_type"),
            since=args.get("since"), until=args.get("until"))
        rows = df_records(df, 50)
        payload = {"n_events": len(df), "events": [
            {k: r[k] for k in ("code", "title", "event_type", "iso3", "bloc_code", "start_date")}
            for r in rows
        ]}
        return ToolOutcome(payload=payload, table=df_table(
            df[["code", "title", "event_type", "start_date", "source"]] if not df.empty else df))

    if name == "event_study":
        df = ed.event_study(
            args["indicator"], event_code=args.get("event_code"),
            event_type=args.get("event_type"),
            window_years=int(args.get("window_years", 3)))
        rows = df_records(df)
        chart = None
        codes = {r["event_code"] for r in rows}
        if len(codes) == 1 and rows:
            ranked = sorted(rows, key=lambda r: abs(r["pct_change"] or 0), reverse=True)[:15]
            chart = {
                "kind": "bar",
                "unit": "% change (after vs before mean)",
                "series": [{
                    "name": next(iter(codes)),
                    "points": [{"x": r["iso3"], "y": r["pct_change"]} for r in ranked],
                }],
            }
        return ToolOutcome(
            payload={"n_rows": len(rows), "rows_sample": rows[:MAX_MODEL_ROWS]},
            chart=chart,
            table=df_table(df),
            indicators=[args["indicator"]],
            warnings=["Event-study deltas compare window means before/after the event; they are descriptive, not causal."],
        )

    if name == "render_chart":
        return _render_chart_outcome(args)

    if name == "correlate":
        lag = int(args.get("lag", 0))
        on = args.get("on", "growth")
        if on not in ("growth", "levels"):
            on = "growth"
        df = ed.lagged_correlation(args["indicator_a"], args["indicator_b"], lag=lag, on=on)
        rows = df_records(df)
        basis = "YoY growth rates" if on == "growth" else "raw levels (trend-inflated)"
        chart = {
            "kind": "bar",
            "unit": "Pearson r",
            "series": [{
                "name": f"{args['indicator_a']} vs {args['indicator_b']}" + (f" (lag {lag})" if lag else ""),
                "points": [{"x": r["iso3"], "y": r["correlation"]} for r in rows[:20]],
            }],
        } if rows else None
        return ToolOutcome(
            payload={"n_countries": len(rows), "basis": on, "rows_sample": rows[:MAX_MODEL_ROWS]},
            chart=chart,
            table=df_table(df),
            indicators=[args["indicator_a"], args["indicator_b"]],
            warnings=[f"Correlation is not causation: per-country Pearson correlations on {basis}, "
                      "with Fisher-z 95% CIs; p-values are unadjusted for multiple comparisons."],
        )

    if name == "forecast":
        horizon = int(args.get("horizon") or 5)
        horizon = max(1, min(horizon, 15))
        df = ed.forecast(args["indicator"], args["country"], horizon=horizon)
        hist = df[df["kind"] == "history"]
        fc = df[df["kind"] == "forecast"]
        unit = df.attrs.get("unit")
        chart = {
            "kind": "line",
            "unit": unit,
            "title": f"{args['indicator']} — {args['country']} (forecast)",
            "series": [
                {"name": args["country"],
                 "points": [{"x": r["period"], "y": r["value"]}
                            for r in df_records(hist)]},
                {"name": f"{args['country']} forecast",
                 "dashed": True,
                 "points": [{"x": r["period"], "y": r["value"]}
                            for r in df_records(fc)],
                 "band": [{"x": r["period"], "lo": r["lo"], "hi": r["hi"]}
                          for r in df_records(fc)]},
            ],
        }
        return ToolOutcome(
            payload={
                "method": df.attrs["method"],
                "fallback": df.attrs["fallback"],
                "backtest_mae": df.attrs["backtest_mae"],
                "disclaimer": df.attrs["disclaimer"],
                "unit": unit,
                "forecast": [{k: r.get(k) for k in ("period", "value", "lo", "hi")}
                             for r in df_records(fc)],
            },
            chart=chart,
            warnings=[df.attrs["disclaimer"]],
        )

    return ToolOutcome(payload={"error": f"Unknown tool: {name}"})
