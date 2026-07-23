"""Chat tool layer and block assembly (Gemini client faked)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(
    not Path("data/eurodata.duckdb").exists(),
    reason="requires the built database (scripts/init_db.py + run_ingestion.py)")

from fastapi.testclient import TestClient  # noqa: E402

from web.backend import deps  # noqa: E402
from web.backend.chat import ChatNotConfiguredError, run_chat  # noqa: E402
from web.backend.main import app  # noqa: E402
from web.backend.tools import execute_tool  # noqa: E402


class FakeClient:
    """Plays back a scripted sequence of Gemini responses."""

    def __init__(self, script):
        self.models = SimpleNamespace(generate_content=lambda **kw: script.pop(0))


def _text_part(t):
    return SimpleNamespace(text=t, function_call=None)


def _call_part(name, args):
    return SimpleNamespace(
        text=None, function_call=SimpleNamespace(name=name, args=args))


def _resp(parts):
    content = SimpleNamespace(role="model", parts=parts)
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


def _no_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_execute_tool_series():
    outcome = execute_tool(deps.get_ed(), "get_series",
                           {"indicator": "GDP", "country": "FRA"})
    assert outcome.payload["n_rows"] > 0
    assert outcome.chart["kind"] == "line"
    assert outcome.chart["series"][0]["points"]
    assert outcome.indicators == ["GDP"]
    assert outcome.table["rows"]


def test_execute_tool_lookup_error_is_payload_not_crash():
    outcome = execute_tool(deps.get_ed(), "get_series", {"indicator": "GPD"})
    assert "GDP" in outcome.payload["error"]


def test_run_chat_assembles_typed_blocks():
    script = [
        _resp([_call_part("get_series", {"indicator": "GDP", "country": "FRA"})]),
        _resp([_text_part("France's GDP grew steadily since 2000.")]),
    ]
    blocks = run_chat([{"role": "user", "content": "How did France's GDP evolve?"}],
                      client=FakeClient(script))
    types_ = [b["type"] for b in blocks]
    assert types_[0] == "text"
    assert "chart" in types_
    assert "sources" in types_ and "follow_ups" in types_
    # The tool outcome still carries a table, but answers no longer dump it
    # under every reply — the chart plus a few quoted figures is the answer.
    assert "table" not in types_
    chart = next(b for b in blocks if b["type"] == "chart")
    assert chart["spec"]["kind"] == "line"
    sources = next(b for b in blocks if b["type"] == "sources")
    assert any("GDP" in item["label"] for item in sources["items"])


def test_execute_tool_render_chart():
    outcome = execute_tool(deps.get_ed(), "render_chart", {
        "kind": "pie",
        "title": "GDP share",
        "unit": "%",
        "series": [{"name": "GDP share", "points": [
            {"x": "DEU", "y": 30}, {"x": "FRA", "y": 25}, {"x": "??", "y": None},
        ]}],
    })
    assert outcome.payload == {"rendered": "pie", "n_series": 1, "n_points": 2}
    assert outcome.chart["kind"] == "pie"
    assert outcome.chart["title"] == "GDP share"
    assert outcome.chart["series"][0]["points"] == [
        {"x": "DEU", "y": 30}, {"x": "FRA", "y": 25}]


def test_execute_tool_render_chart_rejects_bad_kind():
    outcome = execute_tool(deps.get_ed(), "render_chart",
                           {"kind": "sankey", "series": []})
    assert "sankey" in outcome.payload["error"]
    assert outcome.chart is None


def test_run_chat_render_chart_wins_over_auto_chart():
    script = [
        _resp([_call_part("get_series", {"indicator": "GDP", "country": "FRA"})]),
        _resp([_call_part("render_chart", {"kind": "area", "series": [
            {"name": "France GDP",
             "points": [{"x": 2000, "y": 1.0}, {"x": 2001, "y": 1.1}]},
        ]})]),
        _resp([_text_part("Here is the area chart.")]),
    ]
    blocks = run_chat([{"role": "user", "content": "area chart of France GDP"}],
                      client=FakeClient(script))
    chart = next(b for b in blocks if b["type"] == "chart")
    assert chart["spec"]["kind"] == "area"


def test_run_chat_correlation_warning():
    script = [
        _resp([_call_part("correlate", {
            "indicator_a": "Internet Users %", "indicator_b": "GDP per capita",
        })]),
        _resp([_text_part("They are strongly correlated in most countries.")]),
    ]
    blocks = run_chat([{"role": "user", "content": "internet vs gdp?"}],
                      client=FakeClient(script))
    warnings = [b["text"] for b in blocks if b["type"] == "warning"]
    assert any("not causation" in w for w in warnings)


def test_run_chat_requires_key(monkeypatch):
    _no_key(monkeypatch)
    with pytest.raises(ChatNotConfiguredError):
        run_chat([{"role": "user", "content": "hi"}])


def test_chat_endpoint_503_without_key(monkeypatch):
    _no_key(monkeypatch)
    client = TestClient(app)
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hello"}]})
    assert r.status_code == 503
    assert "GOOGLE_API_KEY" in r.json()["detail"]


def test_chat_endpoint_rejects_empty():
    client = TestClient(app)
    r = client.post("/api/chat", json={"messages": []})
    assert r.status_code == 422


def test_forecast_tool_returns_method_and_disclaimer(ed):
    out = execute_tool(ed, "forecast",
                       {"indicator": "GDP per capita", "country": "FRA",
                        "horizon": 3})
    assert "error" not in out.payload
    assert out.payload["method"] in (
        "drift", "linear", "log_linear", "holt", "seasonal_naive", "holt_winters")
    assert "not a prediction" in out.payload["disclaimer"].lower()
    assert len(out.payload["forecast"]) == 3
