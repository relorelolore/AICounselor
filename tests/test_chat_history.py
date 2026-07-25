"""Tests for the stateless history-based WS protocol."""
from __future__ import annotations

import json
import pytest


def _connect(client, payload: dict, timeout: float = 30.0):
    """Connect to /ws/chat, send payload, return a list of events.

    Default 30s — the local reasoning model needs ~9s per call here, so a
    5s ceiling would spuriously time-out success-path tests. Validation
    tests still return within milliseconds so the loop exits early.
    """
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json(payload)
        events: list[dict] = []
        # Read until error or done; protect against hang with a short poll.
        import time
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


def test_single_turn_history(client):
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000001",
        "history": [{"role": "user", "content": "你好"}],
    })
    kinds = [e["event"] for e in events]
    assert "token" in kinds
    assert "done" in kinds
    assert kinds[-1] == "done"


def test_multi_turn_history_accepted(client):
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000002",
        "history": [
            {"role": "user", "content": "第一次"},
            {"role": "assistant", "content": "旧回复"},
            {"role": "user", "content": "第二次"},
        ],
    })
    assert any(e["event"] == "done" for e in events)


def test_empty_history_rejected(client):
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000003",
        "history": [],
    })
    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["data"] == "empty history"


def test_history_must_end_with_user(client):
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000004",
        "history": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
    })
    assert events[0]["event"] == "error"
    assert events[0]["data"] == "history must end with user message"


def test_unknown_role_rejected(client):
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000005",
        "history": [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "garbage"},
        ],
    })
    assert events[0]["event"] == "error"
    assert "unknown role" in events[0]["data"]


def test_total_history_too_long_rejected(client):
    big = "x" * 4001
    events = _connect(client, {
        "session_id": "00000000-0000-4000-8000-000000000006",
        "history": [{"role": "user", "content": big}],
    })
    assert events[0]["event"] == "error"
    assert "too long" in events[0]["data"]


def test_invalid_session_id_rejected(client):
    events = _connect(client, {
        "session_id": "not-a-uuid",
        "history": [{"role": "user", "content": "hi"}],
    })
    assert events[0]["event"] == "error"
    assert events[0]["data"] == "invalid session_id"
