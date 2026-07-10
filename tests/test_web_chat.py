"""Chat tool layer and block assembly (Anthropic client faked)."""
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
    """Plays back a scripted sequence of responses."""

    def __init__(self, script):
        self.messages = SimpleNamespace(create=lambda **kw: script.pop(0))


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool_use(name, args, id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id)


def _resp(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


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
        _resp([_tool_use("get_series", {"indicator": "GDP", "country": "FRA"})],
              "tool_use"),
        _resp([_text("France's GDP grew steadily since 2000.")], "end_turn"),
    ]
    blocks = run_chat([{"role": "user", "content": "How did France's GDP evolve?"}],
                      client=FakeClient(script))
    types = [b["type"] for b in blocks]
    assert types[0] == "text"
    assert "chart" in types and "table" in types
    assert "sources" in types and "follow_ups" in types
    chart = next(b for b in blocks if b["type"] == "chart")
    assert chart["spec"]["kind"] == "line"
    sources = next(b for b in blocks if b["type"] == "sources")
    assert any("GDP" in item["label"] for item in sources["items"])


def test_run_chat_correlation_warning():
    script = [
        _resp([_tool_use("correlate", {
            "indicator_a": "Internet Users %", "indicator_b": "GDP per capita",
        })], "tool_use"),
        _resp([_text("They are strongly correlated in most countries.")], "end_turn"),
    ]
    blocks = run_chat([{"role": "user", "content": "internet vs gdp?"}],
                      client=FakeClient(script))
    warnings = [b["text"] for b in blocks if b["type"] == "warning"]
    assert any("not causation" in w for w in warnings)


def test_run_chat_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ChatNotConfiguredError):
        run_chat([{"role": "user", "content": "hi"}])


def test_chat_endpoint_503_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(app)
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "hello"}]})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_chat_endpoint_rejects_empty():
    client = TestClient(app)
    r = client.post("/api/chat", json={"messages": []})
    assert r.status_code == 422
