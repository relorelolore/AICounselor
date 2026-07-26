"""Tests for routes_chat.py::_strip_reasoning — strips native model CoT
(<think>, <reasoning>, <analysis>, etc.) from the AI's reply text before it
is sent over the WebSocket.

Default behavior: strip (ordinary users never see reasoning).
Debug toggle: WS request with `show_reasoning: true` preserves the raw content.

Pure-function tests cover the regex exhaustively. WS-level test exercises the
end-to-end pipeline via TestClient.websocket_connect with a graph mock that
returns a fixed AIMessage.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes_chat import _strip_reasoning


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------

def test_strips_think_qwen_style():
    out = _strip_reasoning("<think>reasoning here</think>\n\n你好！", show=False)
    assert out == "你好！"


def test_strips_reasoning_tag():
    out = _strip_reasoning(
        "<reasoning>thinking</reasoning>\nanswer", show=False
    )
    assert out == "answer"


def test_strips_special_token_reasoning():
    out = _strip_reasoning(
        "<|reasoning|>deep thought</|reasoning|>\nresponse", show=False
    )
    assert out == "response"


def test_strips_reflection():
    out = _strip_reasoning(
        "<reflection>self-check</reflection>\nfinal", show=False
    )
    assert out == "final"


def test_strips_analysis():
    out = _strip_reasoning(
        "<analysis>analytical step</analysis>\nanswer body", show=False
    )
    assert out == "answer body"


def test_strips_scratchpad_anthropic_style():
    out = _strip_reasoning(
        "<scratchpad>internal monologue</scratchpad>\nfinal answer",
        show=False,
    )
    assert out == "final answer"


def test_strips_thinking_generic():
    out = _strip_reasoning(
        "<thinking>reasoning</thinking>\nconclusion", show=False
    )
    assert out == "conclusion"


def test_strips_plan():
    out = _strip_reasoning("<plan>steps</plan>\nact", show=False)
    assert out == "act"


def test_strips_cross_line_thinking():
    src = "<think>\nline one\nline two\n\n\n</think>\nanswer"
    out = _strip_reasoning(src, show=False)
    assert out == "answer"


def test_strips_multiple_thinking_blocks():
    src = "<think>first</think> A <reasoning>second</reasoning> B <reflection>third</reflection> C"
    out = _strip_reasoning(src, show=False)
    # All three CoT blocks removed; surrounding whitespace kept verbatim
    # (no whitespace collapsing — preserves paragraph structure the model
    # emitted; downstream markdown renders runs of \n as block separators).
    assert out.replace(" ", "") == "ABC"
    assert "<think>" not in out and "<reasoning>" not in out and "<reflection>" not in out


def test_preserves_unclosed_thinking_block():
    """Missing close tag must NOT delete everything after the open tag —
    regex requires a matched pair, otherwise the block is preserved as-is
    (and likely surfaces in the chat, which is the safer failure mode for
    debugging model output)."""
    src = "<think>no close\nrest of answer"
    out = _strip_reasoning(src, show=False)
    assert out == src


def test_preserves_unknown_format():
    """<cot> is not in _REASONING_PAIRS — preserved as-is."""
    src = "<cot>internal</cot> final"
    out = _strip_reasoning(src, show=False)
    assert out == src


def test_no_thinking_unchanged():
    src = "纯回答无任何 reasoning 标签"
    out = _strip_reasoning(src, show=False)
    assert out == src


def test_empty_string_unchanged():
    assert _strip_reasoning("", show=False) == ""


def test_show_true_preserves_everything():
    src = "<think>kept</think>\nanswer"
    assert _strip_reasoning(src, show=True) == src


def test_strip_then_strip_whitespace():
    """Trailing/leading whitespace after strip is removed."""
    assert _strip_reasoning("<think>x</think>\n\n", show=False) == ""
    assert _strip_reasoning("\n\n<think>x</think>\n", show=False) == ""


# ---------------------------------------------------------------------------
# WS-level integration test (default + debug toggle)
# ---------------------------------------------------------------------------

class _FixedGraph:
    """Mock graph whose ainvoke returns a fixed final_state, mimicking the
    shape produced by LangGraph after a ReAct turn."""

    def __init__(self, content: str):
        from langchain_core.messages import AIMessage
        self._msg = AIMessage(content=content)

    async def ainvoke(self, state, config=None):
        return {"messages": [self._msg]}


class _FakeRetriever:
    """Stub retriever; routes_chat.get_retriever is patched at the call site
    to return this so no real Chroma query fires."""

    def __init__(self):
        self.k = 6

    def invoke(self, query, config=None):
        return []


def _build_client_with_mock_graph(monkeypatch, ai_content: str) -> TestClient:
    """Return a TestClient whose chat route uses our mock graph."""
    # Patch at the call sites inside routes_chat.chat (the function imports
    # them lazily). Lazy import: we patch the names in the module's globals.
    import app.routes_chat as rc

    monkeypatch.setattr(rc, "build_graph", lambda *, llm, retriever: _FixedGraph(ai_content))
    monkeypatch.setattr(rc, "get_retriever", lambda k=6: _FakeRetriever())
    monkeypatch.setattr(rc, "get_llm", lambda *, streaming=True: object())

    return TestClient(app)


def _connect(client, payload: dict, timeout: float = 5.0) -> list[dict]:
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json(payload)
        events: list[dict] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                ev = ws.receive_json()
            except Exception:
                break
            events.append(ev)
            if ev.get("event") in ("done", "error"):
                break
        return events


_RAW = (
    "<think>The user is just greeting me. According to the instructions, "
    "I don't need to search documents for simple greetings or chitchat. "
    "I should respond naturally and briefly.</think>\n\n"
    "你好！我是小辅，有什么关于培养方案、课程或毕业要求的问题可以问我～"
)


def test_ws_strips_thinking_by_default(monkeypatch):
    client = _build_client_with_mock_graph(monkeypatch, _RAW)
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000010",
        "history": [{"role": "user", "content": "你好"}],
    })
    tokens = [e["data"] for e in events if e["event"] == "token"]
    assert len(tokens) == 1
    assert "<think>" not in tokens[0]
    assert "thinking" not in tokens[0].lower()
    assert "你好！我是小辅" in tokens[0]


def test_ws_preserves_thinking_when_flag(monkeypatch):
    client = _build_client_with_mock_graph(monkeypatch, _RAW)
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000011",
        "history": [{"role": "user", "content": "你好"}],
        "show_reasoning": True,
    })
    tokens = [e["data"] for e in events if e["event"] == "token"]
    assert len(tokens) == 1
    # Raw content preserved end-to-end when debug toggle on.
    assert tokens[0] == _RAW


def test_ws_show_reasoning_false_keeps_strip(monkeypatch):
    """Explicit False behaves the same as omitted."""
    client = _build_client_with_mock_graph(monkeypatch, _RAW)
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000012",
        "history": [{"role": "user", "content": "你好"}],
        "show_reasoning": False,
    })
    tokens = [e["data"] for e in events if e["event"] == "token"]
    assert len(tokens) == 1
    assert "<think>" not in tokens[0]


def test_ws_skips_token_event_when_strip_empties_content(monkeypatch):
    """If the model emits only <think>...</think> and nothing else, the
    client should receive no token event (no empty content leaks)."""
    only_thinking = "<think>all thinking, no real answer</think>"
    client = _build_client_with_mock_graph(monkeypatch, only_thinking)
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000013",
        "history": [{"role": "user", "content": "你好"}],
    })
    token_events = [e for e in events if e["event"] == "token"]
    assert token_events == []
    # Still emits done so the client knows the turn completed.
    assert any(e["event"] == "done" for e in events)


# ---------------------------------------------------------------------------
# Admin-settings OR-semantics: WS payload flag OR admin debug.show_reasoning.
# ---------------------------------------------------------------------------

def test_ws_admin_debug_setting_overrides_strip(monkeypatch):
    """admin enabled debug.show_reasoning globally → WS without show_reasoning
    flag still preserves CoT (admin setting wins for global debug)."""
    import app.routes_chat as rc
    monkeypatch.setattr(
        rc, "get_effective_settings",
        lambda: {
            "llm": {}, "retrieval": {}, "paths": {}, "embedding": {},
            "debug": {"show_reasoning": True},
        },
    )

    client = _build_client_with_mock_graph(monkeypatch, _RAW)
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000020",
        "history": [{"role": "user", "content": "你好"}],
        # No show_reasoning in payload — admin setting should still apply.
    })
    tokens = [e["data"] for e in events if e["event"] == "token"]
    assert len(tokens) == 1
    assert tokens[0] == _RAW


def test_ws_or_semantics_url_flag_overrides_admin_off(monkeypatch):
    """URL flag set → admin setting off → CoT still preserved (OR)."""
    import app.routes_chat as rc
    monkeypatch.setattr(
        rc, "get_effective_settings",
        lambda: {
            "llm": {}, "retrieval": {}, "paths": {}, "embedding": {},
            "debug": {"show_reasoning": False},
        },
    )

    client = _build_client_with_mock_graph(monkeypatch, _RAW)
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000021",
        "history": [{"role": "user", "content": "你好"}],
        "show_reasoning": True,
    })
    tokens = [e["data"] for e in events if e["event"] == "token"]
    assert len(tokens) == 1
    assert tokens[0] == _RAW


def test_ws_or_semantics_both_off_strips(monkeypatch):
    """Both off (admin default + no URL flag) → strip."""
    import app.routes_chat as rc
    monkeypatch.setattr(
        rc, "get_effective_settings",
        lambda: {
            "llm": {}, "retrieval": {}, "paths": {}, "embedding": {},
            "debug": {"show_reasoning": False},
        },
    )

    client = _build_client_with_mock_graph(monkeypatch, _RAW)
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000022",
        "history": [{"role": "user", "content": "你好"}],
    })
    tokens = [e["data"] for e in events if e["event"] == "token"]
    assert len(tokens) == 1
    assert "<think>" not in tokens[0]


def test_ws_admin_section_missing_falls_back_to_false(monkeypatch):
    """Defensive: if `debug` section is absent (DB partial state), treat
    show_reasoning as False (don't accidentally leak CoT)."""
    import app.routes_chat as rc
    monkeypatch.setattr(
        rc, "get_effective_settings",
        lambda: {"llm": {}, "retrieval": {}, "paths": {}, "embedding": {}},
    )

    client = _build_client_with_mock_graph(monkeypatch, _RAW)
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000023",
        "history": [{"role": "user", "content": "你好"}],
    })
    tokens = [e["data"] for e in events if e["event"] == "token"]
    assert "<think>" not in tokens[0]