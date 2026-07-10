"""The AI analyst: Claude tool-use loop + typed response blocks.

``run_chat`` takes the conversation as [{"role", "content"}] text messages,
lets the model call the read-only tools in tools.py, then assembles the
response the frontend renders: a list of typed blocks —
text / chart / table / sources / warning / follow_ups.
"""
from __future__ import annotations

import json
import os
from typing import Any

from web.backend import deps
from web.backend.tools import TOOL_DEFS, ToolOutcome, df_records, execute_tool

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TURNS = 8

SYSTEM_PROMPT = """You are the eurodata AI analyst: a European open-data analyst \
answering questions over a DuckDB dataset of official statistics (26 indicators \
across economy, demographics, digital, energy & climate, AI & technology; ~50 \
European countries; 2000-2025) plus a curated table of dated European events.

Rules:
- Use the tools to fetch data before answering any factual question. Never \
invent numbers. If a lookup fails, use search_indicators and retry with the \
suggested name.
- Be provenance-first: name the data source, and say explicitly when an \
indicator is a proxy for the official concept.
- Correlation is not causation; say so whenever you discuss correlations or \
event studies.
- Be concise: a short paragraph of insight. The UI renders charts and tables \
from your tool calls automatically, so do not write out long lists of numbers \
or ASCII tables.
- Only answer from this dataset. If the question is outside European open \
data, say what you can and cannot answer."""


class ChatNotConfiguredError(RuntimeError):
    """No Anthropic API key configured."""


def _client_or_raise(client: Any | None) -> Any:
    if client is not None:
        return client
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ChatNotConfiguredError(
            "The AI analyst is not configured: set ANTHROPIC_API_KEY in the "
            "backend environment (see .env.example).")
    import anthropic

    return anthropic.Anthropic()


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
    table_outcome = next((o for o in reversed(outcomes) if o.table), None)
    if table_outcome and table_outcome.table["rows"]:
        blocks.append({"type": "table", **table_outcome.table})

    # provenance chips: one per (indicator, source) touched
    touched = {(ind, src) for o in outcomes for ind in o.indicators
               for src in (o.sources or [None])}
    if touched:
        with deps.lock:
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


def run_chat(messages: list[dict[str, str]], *, client: Any | None = None,
             model: str | None = None, ed=None) -> list[dict[str, Any]]:
    client = _client_or_raise(client)
    model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    ed = ed or deps.get_ed()

    convo: list[dict[str, Any]] = [
        {"role": m["role"], "content": m["content"]} for m in messages
    ]
    outcomes: list[ToolOutcome] = []
    tools_used: list[str] = []
    final_text = ""

    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=model, max_tokens=1500, system=SYSTEM_PROMPT,
            tools=TOOL_DEFS, messages=convo)
        final_text = "\n\n".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text")
        if resp.stop_reason != "tool_use":
            break
        convo.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            tools_used.append(block.name)
            with deps.lock:
                outcome = execute_tool(ed, block.name, dict(block.input))
            outcomes.append(outcome)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(outcome.payload, default=str),
            })
        convo.append({"role": "user", "content": results})

    return _assemble_blocks(final_text, outcomes, tools_used, ed)
