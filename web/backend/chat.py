"""The AI analyst: Gemini function-calling loop + typed response blocks.

``run_chat`` takes the conversation as [{"role", "content"}] text messages,
lets the model call the read-only tools in tools.py, then assembles the
response the frontend renders: a list of typed blocks —
text / chart / sources / warning / follow_ups.

Tool outcomes still carry a `table`, but the assembler no longer emits a
table block: a raw data dump under every answer was noise. The frontend
keeps its table renderer for the Explore/Events pages, which ask for one.
"""
from __future__ import annotations

import os
from typing import Any

from eurodata.reference.catalog import DOMAINS, INDICATORS
from eurodata.reference.countries import COUNTRIES
from web.backend import deps
from web.backend.tools import TOOL_DEFS, ToolOutcome, df_records, execute_tool

DEFAULT_MODEL = "gemini-flash-latest"
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3-flash-preview"]
MAX_TURNS = 8

# Dataset facts come from the catalog so the prompt cannot drift from the data.
_DOMAIN_NAMES = ", ".join(d["name"] for d in DOMAINS)

SYSTEM_PROMPT = f"""You are the eurodata AI analyst: a European open-data analyst \
answering questions over a DuckDB dataset of official statistics \
({len(INDICATORS)} indicators across {_DOMAIN_NAMES}; \
{len(COUNTRIES)} European countries; 2000-2025) plus a curated table of dated \
European events.

Most indicators are annual; a few are monthly or quarterly (interest rates, \
exchange rates, monthly HICP, quarterly GDP growth, monthly unemployment) — \
their rows carry a period label like 2022-03 or 2022-Q1. Prefer sub-annual \
series when the question is about timing around events.

Rules:
- Use the tools to fetch data before answering any factual question. Never \
invent numbers. If a lookup fails, use search_indicators and retry with the \
suggested name.
- Be provenance-first: name the data source, and say explicitly when an \
indicator is a proxy for the official concept.
- Correlation is not causation; say so whenever you discuss correlations or \
event studies.
- Be concise: a short paragraph of insight. The UI renders charts from your \
tool calls automatically, so do not write out long lists of numbers, markdown \
tables or ASCII tables. Quote only the few figures your point rests on.
- If the user asks for a specific kind of chart, diagram or graph (pie, \
scatter, area, bar, line...), first fetch the data with the other tools, then \
call render_chart with points taken from those results. Never draw charts in \
text.
- When you use the forecast tool, always state which method it chose and lead \
with its disclaimer — never present a forecast as a certain prediction.
- Only answer from this dataset. If the question is outside European open \
data, say what you can and cannot answer."""


class ChatNotConfiguredError(RuntimeError):
    """No Google API key configured."""


def _client_or_raise(client: Any | None) -> Any:
    if client is not None:
        return client
    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        raise ChatNotConfiguredError(
            "The AI analyst is not configured: set GOOGLE_API_KEY in the "
            "backend environment (see .env.example).")
    from google import genai

    return genai.Client()


def _generation_config() -> Any:
    from google.genai import types

    decls = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters_json_schema=t["input_schema"],
        )
        for t in TOOL_DEFS
    ]
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=decls)],
        max_output_tokens=2000,
    )


def _follow_ups(outcomes: list[ToolOutcome], tools_used: list[str]) -> list[str]:
    indicators = []
    for o in outcomes:
        for ind in o.indicators:
            if ind not in indicators:
                indicators.append(ind)
    ideas: list[str] = []
    if indicators and "event_study" not in tools_used:
        ideas.append(f"How did {indicators[0]} change around the 2021 energy crisis?")
    if indicators and "correlate" not in tools_used:
        other = "GDP per capita" if indicators[0] != "GDP per capita" else "Internet Users %"
        ideas.append(f"Correlate {indicators[0]} with {other}")
    if "latest" not in tools_used and indicators:
        ideas.append(f"Rank EU countries by {indicators[0]}")
    if not indicators:
        ideas = [
            "What data do you have?",
            "Compare unemployment in France, Germany and Italy",
            "Which events affected inflation the most?",
        ]
    return ideas[:3]


def _assemble_blocks(final_text: str, outcomes: list[ToolOutcome],
                     tools_used: list[str], ed) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if final_text.strip():
        blocks.append({"type": "text", "text": final_text.strip()})

    chart_outcome = next((o for o in reversed(outcomes) if o.chart), None)
    if chart_outcome:
        blocks.append({"type": "chart", "spec": chart_outcome.chart})

    # provenance chips: one per (indicator, source) touched
    touched = {(ind, src) for o in outcomes for ind in o.indicators
               for src in (o.sources or [None])}
    if touched:
        meta = {r["name"]: r for r in df_records(ed.indicators())}
        source_urls = {r["name"]: r["url"] for r in df_records(ed.sources())}
        items = []
        for ind, src in sorted(touched, key=lambda t: (t[0], str(t[1]))):
            m = meta.get(ind, {})
            items.append({
                "label": f"{ind} · {src}" if src else ind,
                "url": source_urls.get(src),
                "is_proxy": bool(m.get("is_proxy")),
                "proxy_note": m.get("proxy_note"),
            })
        blocks.append({"type": "sources", "items": items})

    seen: set[str] = set()
    for o in outcomes:
        for w in o.warnings:
            if w not in seen:
                seen.add(w)
                blocks.append({"type": "warning", "text": w})

    blocks.append({"type": "follow_ups", "items": _follow_ups(outcomes, tools_used)})
    return blocks


def _generate_with_retry(client: Any, model: str, contents: list[Any],
                         config: Any) -> Any:
    """One model turn, riding out transient 429/503s and retired models.

    Tries the configured model with backoff, then each fallback once.
    """
    import time

    last_exc: Exception | None = None
    candidates = [model] + [m for m in FALLBACK_MODELS if m != model]
    for i, m in enumerate(candidates):
        attempts = 3 if i == 0 else 1
        for attempt in range(attempts):
            try:
                return client.models.generate_content(
                    model=m, contents=contents, config=config)
            except Exception as exc:
                code = getattr(exc, "code", None)
                if code not in (404, 429, 503):
                    raise
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def run_chat(messages: list[dict[str, str]], *, client: Any | None = None,
             model: str | None = None, ed=None) -> list[dict[str, Any]]:
    client = _client_or_raise(client)
    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    ed = ed or deps.get_ed()

    from google.genai import types

    contents: list[Any] = [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in messages
    ]
    config = _generation_config()
    outcomes: list[ToolOutcome] = []
    tools_used: list[str] = []
    final_text = ""

    for _ in range(MAX_TURNS):
        resp = _generate_with_retry(client, model, contents, config)
        cand = resp.candidates[0] if resp.candidates else None
        parts = list(cand.content.parts or []) if cand and cand.content else []
        final_text = "\n\n".join(
            p.text for p in parts if getattr(p, "text", None))
        calls = [p.function_call for p in parts
                 if getattr(p, "function_call", None)]
        if not calls:
            break
        contents.append(cand.content)
        response_parts = []
        for fc in calls:
            tools_used.append(fc.name)
            outcome = execute_tool(ed, fc.name, dict(fc.args or {}))
            outcomes.append(outcome)
            response_parts.append(types.Part.from_function_response(
                name=fc.name, response={"result": outcome.payload}))
        # the SDK's own function-calling loop sends responses as role="user"
        contents.append(types.Content(role="user", parts=response_parts))

    return _assemble_blocks(final_text, outcomes, tools_used, ed)
