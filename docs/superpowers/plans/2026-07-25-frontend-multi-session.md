# Frontend Multi-Session + Stateless Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-session, server-persisted chat with a multi-session, client-localStorage-only UI (ChatGPT-style sidebar layout) and refactor the backend into a stateless ReAct runner that takes the full conversation history per request.

**Architecture:** Frontend keeps a single `app.js` module with internal sections (store / wsClient / renderer / markdown / actions / input / sidebar / boot) holding all sessions in `localStorage["counselor:state"]`. Backend (`app/routes_chat.py`) accepts `{session_id, history:[{role,content}, ...]}` and runs `graph.ainvoke({messages: [...]})` with **no checkpointer**; citations are extracted only from `ToolMessage`s produced *after* the last `HumanMessage` in the history so prior turns never leak.

**Tech Stack:** FastAPI + WebSocket; LangChain `langgraph.prebuilt.create_react_agent`; vanilla JS (no framework, no build step); CSS Grid + custom properties; `localStorage`.

## Global Constraints

From the spec + CLAUDE.md, applicable to every task unless that task overrides:

- Python: `.venv` via `uv`; **never** `pip` / `python -m pytest`; always `uv run --extra dev pytest` (and `OFFLINE=1` to skip bge-m3 download).
- Frontend: no npm, no bundler. `web/index.html`, `web/style.css`, `web/app.js` only.
- Static files must keep `Cache-Control: no-store` (existing `app/static_no_store.py`).
- Frontend cache-bust query string must increment monotonically; old value is `v=4`.
- Tests live under `tests/` with **no `__init__.py`** (pytest rootdir auto-discovery).
- `OFFLINE=1` skips bge-m3; live llama.cpp at `http://localhost:8848/v1` may be down — tests must not require it.
- WS events from server: `token`, `citation`, `done`, `error` (existing protocol).
- HTTP errors are sanitized (`ErrorEvent` with truncated message); never leak stack traces to the client.
- `storage/paths.py` is the single source of disk paths; do not hardcode elsewhere.

---

### Task 1: Backend — Stateless WS handler accepting `history`

**Files:**
- Modify: `app/routes_chat.py` (entire file rewrite)
- Create: `tests/test_chat_history.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - WS first-frame JSON: `{session_id: str, history: [{role: "user"|"assistant", content: str}, ...]}`
  - Errors (sent as `{"event":"error","data":"..."}` then close): `"empty history"`, `"history must end with user message"`, `"history item <i> has unknown role"`, `"history item <i> content too long"`, `"history too long (N>4000)"`, `"invalid session_id"`.

**Background:**
The current handler reads a flat `message` string, builds a one-element `messages` list, wraps the graph in `AsyncSqliteSaver`, snapshots prior state to diff citations, and uses `thread_id` config. We replace all four: read `history`, construct full `messages`, run with no checkpointer, and extract citations by walking from the last `HumanMessage` forward.

- [ ] **Step 1: Write failing tests for the new protocol**

Create `tests/test_chat_history.py`:

```python
"""Tests for the stateless history-based WS protocol."""
from __future__ import annotations

import json
import pytest


def _connect(client, payload: dict, timeout: float = 5.0):
    """Connect to /ws/chat, send payload, return a list of events."""
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
```

Use the same `client` fixture already defined in `tests/test_api.py` — extract it into `tests/conftest.py` (see step 2).

- [ ] **Step 2: Extract shared `client` fixture into `tests/conftest.py`**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures for API tests."""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "Documents"))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setenv("OFFLINE", "1")
    # Reset singletons so each test gets a clean app.
    import rag.embeddings as emb_mod
    importlib.reload(emb_mod)
    import rag.retriever as ret_mod
    importlib.reload(ret_mod)
    import llm.client as llm_client_mod
    importlib.reload(llm_client_mod)
    import app.main as app_main_mod
    importlib.reload(app_main_mod)
    return TestClient(app_main_mod.app)
```

Then delete the local `client` fixture and the `import tempfile` from `tests/test_api.py` so they import from `conftest.py`. Make the imports lean:

```python
# tests/test_api.py (top of file only)
from fastapi.testclient import TestClient
import pytest
```

(`TestClient` and `pytest` are no longer used here but kept to avoid touching unrelated imports.)

- [ ] **Step 3: Run new tests and watch them fail**

Run:
```bash
OFFLINE=1 uv run --extra dev pytest tests/test_chat_history.py -v
```
Expected: ALL tests fail (either connection refused because old handler expects `message`, or payload validation rejects `history`).

- [ ] **Step 4: Rewrite `app/routes_chat.py`**

Replace the whole file with:

```python
# app/routes_chat.py
from __future__ import annotations

import json
import traceback
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from .schemas import ErrorEvent
from agent.graph import build_graph
from llm.client import get_llm
from rag.citations import to_citations
from rag.retriever import get_retriever


router = APIRouter()


# Per-history-item content cap (chars). Combined total cap is enforced separately.
_MAX_ITEM_CHARS = 4000
# Combined history content cap.
_MAX_HISTORY_CHARS = 4000 * 20  # 80 000 chars; ~20 turns of long messages


_VALID_ROLES = {"user", "assistant"}


def _validate_session_id(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except Exception:
        return False


def _validate_history(raw) -> tuple[list[dict] | None, str | None]:
    """Return (normalized_history, error_message)."""
    if not isinstance(raw, list) or len(raw) == 0:
        return None, "empty history"
    total = 0
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return None, f"history item {i} not an object"
        role = item.get("role")
        if role not in _VALID_ROLES:
            return None, f"history item {i} has unknown role: {role!r}"
        content = item.get("content", "")
        if not isinstance(content, str):
            return None, f"history item {i} content not a string"
        if len(content) > _MAX_ITEM_CHARS:
            return None, f"history item {i} content too long ({len(content)}>{_MAX_ITEM_CHARS})"
        total += len(content)
    if raw[-1]["role"] != "user":
        return None, "history must end with user message"
    if total > _MAX_HISTORY_CHARS:
        return None, f"history too long ({total}>{_MAX_HISTORY_CHARS})"
    return raw, None


def _history_to_messages(history: list[dict]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for item in history:
        if item["role"] == "user":
            out.append(HumanMessage(content=item["content"]))
        else:
            out.append(AIMessage(content=item["content"]))
    return out


def _extract_current_turn_citations(messages: list[BaseMessage]) -> list[dict]:
    """Citations from search_documents ToolMessages produced AFTER the
    last HumanMessage in the conversation.

    This prevents citations from prior turns leaking into the current
    turn's response when the user keeps the same chat session.
    """
    last_human_idx = -1
    for i, m in enumerate(messages):
        if isinstance(m, HumanMessage):
            last_human_idx = i
    out: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for m in messages[last_human_idx + 1:]:
        if isinstance(m, ToolMessage) and m.name == "search_documents":
            for cite in to_citations(m.artifact or []):
                key = (cite["filename"], cite["page"])
                if key not in seen:
                    seen.add(key)
                    out.append(cite)
    return out


@router.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        raw = await ws.receive_text()
        payload = json.loads(raw)
        session_id = str(payload.get("session_id", ""))
        history = payload.get("history")

        if not _validate_session_id(session_id):
            await ws.send_text(ErrorEvent(data="invalid session_id").model_dump_json())
            await ws.close()
            return

        normalized, err = _validate_history(history)
        if err is not None:
            await ws.send_text(ErrorEvent(data=err).model_dump_json())
            await ws.close()
            return

        llm = get_llm(streaming=True)
        retriever = get_retriever(k=6)
        graph = build_graph(llm=llm, retriever=retriever)
        messages = _history_to_messages(normalized)

        try:
            final_state = await graph.ainvoke({"messages": messages})

            ai_messages = [
                m for m in final_state["messages"] if isinstance(m, AIMessage)
            ]
            if ai_messages:
                ai_content = ai_messages[-1].content or ""
                if ai_content:
                    await ws.send_text(json.dumps(
                        {"event": "token", "data": ai_content}, ensure_ascii=False))

            citations = _extract_current_turn_citations(final_state["messages"])
            if citations:
                await ws.send_text(json.dumps(
                    {"event": "citation", "data": citations}, ensure_ascii=False))

            await ws.send_text(json.dumps(
                {"event": "done", "data": {"finish_reason": "stop"}},
                ensure_ascii=False))
        except WebSocketDisconnect:
            return
        except Exception as exc:                              # noqa: BLE001
            exc_name = type(exc).__name__
            exc_msg = str(exc)[:200]
            print(
                f"[chat] agent error: {exc_name}: {exc}\n{traceback.format_exc()}",
                file=__import__("sys").stderr,
            )
            await ws.send_text(ErrorEvent(
                data=f"agent error ({exc_name}): {exc_msg}"
            ).model_dump_json())
            await ws.close()
            return

    except WebSocketDisconnect:
        return
    except Exception as exc:                                     # noqa: BLE001
        exc_name = type(exc).__name__
        exc_msg = str(exc)[:200]
        print(
            f"[chat] unexpected error: {exc_name}: {exc}\n{traceback.format_exc()}",
            file=__import__("sys").stderr,
        )
        try:
            await ws.send_text(ErrorEvent(
                data=f"unexpected: ({exc_name}): {exc_msg}"
            ).model_dump_json())
        except Exception:
            pass
```

- [ ] **Step 5: Run all new tests + full suite**

Run:
```bash
OFFLINE=1 uv run --extra dev pytest tests/test_chat_history.py tests/test_api.py -v
```
Expected: All 7 new tests pass; existing `test_api.py` tests still pass.

If `test_health_returns_struct` or `test_ingest_runs_with_empty_corpus` regresses, check that `app/routes_chat.py` no longer imports `AsyncSqliteSaver` (which is no longer used and would prevent import of `langgraph.checkpoint.sqlite.aio` if it had side effects).

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_chat_history.py tests/test_api.py app/routes_chat.py
git commit -m "feat(chat): stateless WS protocol accepting full history per request

Replaces single-message frame with {session_id, history:[...]} so the
backend no longer needs a per-session checkpointer. Citations are now
extracted from ToolMessages produced AFTER the last HumanMessage in
history, preventing prior-turn leakage when a chat session is reused.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Backend — Drop SqliteSaver + checkpoint DB

**Files:**
- Modify: `agent/graph.py` (make `checkpointer` optional)
- Modify: `storage/paths.py` (drop `CHECKPOINT_DB`)
- Modify: `scripts/run.sh` (one-time migration: rm old checkpoints.db)
- Modify: `CLAUDE.md` (drop SqliteSaver pitfalls)

**Interfaces:**
- `build_graph(*, llm, retriever, checkpointer=None)` — `checkpointer` is now keyword-only and optional.

- [ ] **Step 1: Verify `build_graph` still accepts `checkpointer`**

Run:
```bash
OFFLINE=1 uv run --extra dev pytest tests/test_graph.py -v
```
Expected: all pass (these tests pass `checkpointer=InMemorySaver()` explicitly). No code change yet — confirms the contract.

- [ ] **Step 2: Make `checkpointer` optional and default to None in `agent/graph.py`**

Edit `agent/graph.py`:

Replace the `build_graph` signature line:

```python
def build_graph(*, llm, retriever, checkpointer=None):
```

(Add `=None`; everything else unchanged.)

The body already handles `checkpointer=None` because `create_react_agent(checkpointer=None)` is valid in `langgraph 0.6.x`.

- [ ] **Step 3: Drop `CHECKPOINT_DB` from `storage/paths.py`**

Edit `storage/paths.py`. Remove the line:
```python
CHECKPOINT_DB: str = os.path.join(DATA_DIR, "checkpoints.db")
```
and the comment if any references it. Result:

```python
# storage/paths.py
import os


DATA_DIR: str = os.environ.get("DATA_DIR", "./data")
DOCUMENTS_DIR: str = os.environ.get("DOCUMENTS_DIR", "./Documents")
WEB_DIR: str = os.environ.get("WEB_DIR", "./web")
CHROMA_DIR: str = os.path.join(DATA_DIR, "chroma")
INDEX_META: str = os.path.join(DATA_DIR, "index_meta.json")
```

- [ ] **Step 4: Add one-time migration in `scripts/run.sh`**

Append to `scripts/run.sh` (just before `mkdir -p data` is fine, or just after the existing `if [ ! -d data/chroma ]` block; either works):

```bash
# One-time migration: drop legacy per-session checkpoint DB. The backend
# is now stateless; persistence lives entirely in the browser's
# localStorage. Safe to leave in — it only acts when the file exists.
rm -f data/checkpoints.db
```

- [ ] **Step 5: Update `CLAUDE.md` — drop SqliteSaver pitfall rows**

Edit `CLAUDE.md`. Find the "已知陷阱" table and:

1. Remove any row mentioning `SqliteSaver`, `checkpoints.db`, `CHECKPOINT_DB`.
2. Find the LangGraph Agent section and rewrite the paragraph that says "多轮历史由 `SqliteSaver` 持久化到 `data/checkpoints.db`" to instead say "后端是无状态的；多轮历史由前端在每次请求时通过 `history` 字段随 WS 一起发送" (match the wording in the new spec §1).
3. Find the section about `session_id` and update: "前端 `localStorage["counselor:state"]` 存所有会话；`session_id = chat.id`，同一会话多次发送沿用同一 id（仅作审计 hook，不参与图运行）。"
4. Bump the "Front/不提供 npm 构建" section to mention the new architecture briefly.

- [ ] **Step 6: Run full test suite**

```bash
OFFLINE=1 uv run --extra dev pytest -q
```
Expected: 39+7 passed, 2 skipped. If any test imports `CHECKPOINT_DB`, fix the import.

- [ ] **Step 7: Commit**

```bash
git add agent/graph.py storage/paths.py scripts/run.sh CLAUDE.md
git commit -m "refactor(backend): drop SqliteSaver; backend is now stateless

build_graph() takes an optional checkpointer (defaults to None).
CHECKPOINT_DB removed from storage/paths.py. scripts/run.sh now deletes
the legacy data/checkpoints.db on each startup (idempotent; safe to
leave). CLAUDE.md updated to reflect the new persistence boundary.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Frontend skeleton — `index.html` and `style.css`

**Files:**
- Rewrite: `web/index.html`
- Rewrite: `web/style.css`
- (no `app.js` changes yet — script tag stays `src="app.js?v=5"`, app.js is still the old single-session one but the HTML structure lays out the new shell)

**Interfaces:**
- IDs the new `app.js` will rely on (defined here in HTML):
  - `#sidebar`, `#sidebar-toggle`, `#new-chat-btn`, `#chat-list`, `#chat-list-groups`
  - `#topbar`, `#chat-title`, `#chat-title-input`, `#chat-actions-menu`, `#status-dot`, `#status-text`, `#reindex`, `#empty-state`, `#empty-state-new`
  - `#messages`, `#message-template`
  - `#input`, `#send`, `#char-count`, `#stop`
  - `#drawer`, `#drawer-close`, `#drawer-body`, `#drawer-backdrop`
  - `#toast`, `#toast-text`

- [ ] **Step 1: Write the new `web/index.html`**

Replace the whole file:

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<meta name="color-scheme" content="light" />
<title>AI 辅导员</title>
<link rel="stylesheet" href="style.css" />
</head>
<body class="sidebar-open">
<div id="toast" hidden><span id="toast-text"></span></div>
<aside id="sidebar" aria-label="会话列表">
  <header class="sidebar-header">
    <button id="sidebar-toggle" type="button" aria-label="折叠侧边栏" title="折叠侧边栏">≡</button>
    <span class="sidebar-brand">AI 辅导员</span>
  </header>
  <button id="new-chat-btn" type="button" class="new-chat">＋ 新会话</button>
  <nav id="chat-list" aria-label="会话"></nav>
</aside>
<main id="main">
  <header id="topbar">
    <button id="sidebar-toggle-inline" type="button" aria-label="展开侧边栏" class="only-collapsed">≡</button>
    <h2 id="chat-title" title="点击重命名" tabindex="0">新会话</h2>
    <input id="chat-title-input" type="text" hidden />
    <div class="topbar-spacer"></div>
    <span class="status"><span id="status-dot" class="dot"></span><span id="status-text">检测中…</span></span>
    <button id="reindex" type="button" title="重建文档索引">重建索引</button>
    <div class="menu-wrap">
      <button id="chat-actions-btn" type="button" aria-label="更多" title="更多">⋯</button>
      <ul id="chat-actions-menu" hidden>
        <li><button type="button" data-act="rename">重命名</button></li>
        <li><button type="button" data-act="delete" class="danger">删除会话</button></li>
        <li><button type="button" data-act="clear-all" class="danger">清空全部会话</button></li>
      </ul>
    </div>
  </header>
  <section id="messages" aria-live="polite"></section>
  <section id="empty-state" hidden>
    <div class="empty-inner">
      <h1>AI 辅导员</h1>
      <p>选个左侧会话继续聊，或者</p>
      <button id="empty-state-new" type="button" class="primary">＋ 新建一个会话</button>
    </div>
  </section>
  <footer id="composer">
    <textarea id="input" rows="1" placeholder="请输入你的问题…" aria-label="输入问题"></textarea>
    <div class="composer-actions">
      <span id="char-count">0</span>/4000
      <button id="send" type="button" class="primary" aria-label="发送">发送</button>
      <button id="stop" type="button" hidden aria-label="停止">停止</button>
    </div>
  </footer>
</main>
<div id="drawer-backdrop" hidden></div>
<aside id="drawer" hidden aria-label="参考资料">
  <header><h3>参考资料</h3><button id="drawer-close" type="button" aria-label="关闭">×</button></header>
  <div id="drawer-body"></div>
</aside>
<template id="message-template">
  <article class="msg">
    <div class="msg-content"></div>
    <div class="msg-cites" hidden></div>
  </article>
</template>
<script src="app.js?v=5"></script>
</body>
</html>
```

- [ ] **Step 2: Write the new `web/style.css`**

Replace the whole file:

```css
/* === Tokens === */
:root {
  --c-bg: #ffffff;
  --c-bg-soft: #fafafa;
  --c-bg-hover: #f1f5f9;
  --c-bg-active: #eff6ff;
  --c-border: #e5e7eb;
  --c-border-strong: #cbd5e1;
  --c-text: #0f172a;
  --c-text-soft: #64748b;
  --c-primary: #2563eb;
  --c-primary-hover: #1d4ed8;
  --c-danger: #dc2626;
  --c-success: #16a34a;
  --c-warn: #d97706;
  --shadow-sm: 0 1px 2px rgba(15, 23, 42, .06);
  --shadow-md: 0 4px 16px rgba(15, 23, 42, .08);
  --shadow-lg: -8px 0 24px rgba(15, 23, 42, .10);
  --radius: 12px;
  --radius-lg: 16px;
  --sidebar-w: 260px;
  --sidebar-w-collapsed: 56px;
  --drawer-w: 320px;
  --header-h: 56px;
  --font: Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
}

@media (prefers-color-scheme: dark) {
  /* Dark mode reserved for v2 — variables are placeholders only */
  :root {
    --c-bg: #0f172a;
    --c-bg-soft: #1e293b;
    --c-bg-hover: #334155;
    --c-bg-active: #1e3a8a;
    --c-border: #334155;
    --c-text: #f1f5f9;
    --c-text-soft: #94a3b8;
  }
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; }
body {
  font-family: var(--font);
  background: var(--c-bg);
  color: var(--c-text);
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;
  overflow: hidden;
}
body.sidebar-collapsed { grid-template-columns: var(--sidebar-w-collapsed) 1fr; }

/* === Sidebar === */
#sidebar {
  background: var(--c-bg-soft);
  border-right: 1px solid var(--c-border);
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.sidebar-header {
  display: flex;
  align-items: center;
  gap: 8px;
  height: var(--header-h);
  padding: 0 12px;
  border-bottom: 1px solid var(--c-border);
}
.sidebar-brand { font-weight: 600; font-size: 14px; white-space: nowrap; }
.sidebar-collapsed .sidebar-brand { display: none; }
#sidebar-toggle {
  background: none; border: none; cursor: pointer;
  font-size: 18px; padding: 6px; border-radius: var(--radius);
  color: var(--c-text);
}
#sidebar-toggle:hover { background: var(--c-bg-hover); }
.sidebar-collapsed #sidebar-toggle { margin: 0 auto; }
.new-chat {
  margin: 12px;
  padding: 10px;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius);
  background: var(--c-bg);
  color: var(--c-text);
  font-weight: 500;
  cursor: pointer;
  transition: background .1s ease;
}
.new-chat:hover { background: var(--c-bg-hover); }
.sidebar-collapsed .new-chat { display: none; }
#chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}
.chat-group-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--c-text-soft);
  text-transform: uppercase;
  letter-spacing: .05em;
  padding: 12px 8px 4px;
}
.sidebar-collapsed .chat-group-title { display: none; }
.chat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 13px;
  color: var(--c-text);
  border-left: 3px solid transparent;
  transition: background .1s ease;
  user-select: none;
}
.chat-item:hover { background: var(--c-bg-hover); }
.chat-item.active {
  background: var(--c-bg-active);
  border-left-color: var(--c-primary);
  font-weight: 500;
}
.chat-item .chat-title-text {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.chat-item .chat-menu-btn {
  background: none; border: none; cursor: pointer;
  padding: 2px 6px; border-radius: 6px; color: var(--c-text-soft);
  opacity: 0; transition: opacity .1s ease;
}
.chat-item:hover .chat-menu-btn, .chat-item.active .chat-menu-btn { opacity: 1; }
.chat-item .chat-menu-btn:hover { background: var(--c-bg-hover); color: var(--c-text); }
.sidebar-collapsed .chat-item { justify-content: center; padding: 8px 4px; }
.sidebar-collapsed .chat-item .chat-title-text,
.sidebar-collapsed .chat-item .chat-menu-btn { display: none; }

/* === Main === */
#main {
  display: grid;
  grid-template-rows: var(--header-h) 1fr auto;
  min-width: 0;
  position: relative;
}
#topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  border-bottom: 1px solid var(--c-border);
  background: var(--c-bg);
}
#topbar h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  cursor: text;
  padding: 4px 8px;
  border-radius: 6px;
  max-width: 40ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
#topbar h2:hover { background: var(--c-bg-hover); }
#chat-title-input {
  font: inherit; font-size: 15px; font-weight: 600;
  border: 1px solid var(--c-border-strong);
  border-radius: 6px;
  padding: 4px 8px;
  background: var(--c-bg);
  color: var(--c-text);
  width: 30ch;
}
.topbar-spacer { flex: 1; }
.status { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--c-text-soft); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-text-soft); display: inline-block; }
.dot.ok { background: var(--c-success); }
.dot.degraded { background: var(--c-warn); }
#reindex, #chat-actions-btn {
  padding: 6px 10px;
  border: 1px solid var(--c-border);
  background: var(--c-bg);
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--c-text);
}
#reindex:hover, #chat-actions-btn:hover { background: var(--c-bg-hover); }
.menu-wrap { position: relative; }
#chat-actions-menu {
  position: absolute; right: 0; top: calc(100% + 4px);
  margin: 0; padding: 4px;
  list-style: none;
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  z-index: 100;
  min-width: 160px;
}
#chat-actions-menu button {
  width: 100%; text-align: left;
  padding: 8px 12px; border: none; background: none;
  font: inherit; color: var(--c-text); border-radius: 6px;
  cursor: pointer;
}
#chat-actions-menu button:hover { background: var(--c-bg-hover); }
#chat-actions-menu .danger { color: var(--c-danger); }
#chat-actions-menu .danger:hover { background: #fef2f2; }
.only-collapsed { display: none; }
.sidebar-collapsed .only-collapsed { display: inline-flex; }

/* === Messages === */
#messages {
  overflow-y: auto;
  padding: 24px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  scroll-behavior: smooth;
}
.msg { display: flex; flex-direction: column; max-width: 80%; }
.msg.user { align-self: flex-end; align-items: flex-end; max-width: 70%; }
.msg-content {
  padding: 10px 14px;
  border-radius: var(--radius-lg);
  line-height: 1.55;
  word-break: break-word;
  white-space: pre-wrap;
  box-shadow: var(--shadow-sm);
}
.msg.user .msg-content {
  background: var(--c-primary);
  color: white;
  border-bottom-right-radius: 4px;
}
.msg.assistant .msg-content {
  background: var(--c-bg-soft);
  border: 1px solid var(--c-border);
  border-bottom-left-radius: 4px;
}
.msg-content h1, .msg-content h2, .msg-content h3 {
  margin: 8px 0 4px;
  font-weight: 600;
}
.msg-content h1 { font-size: 1.15em; }
.msg-content h2 { font-size: 1.05em; }
.msg-content h3 { font-size: 1em; }
.msg-content ul, .msg-content ol { margin: 4px 0 4px 18px; padding: 0; }
.msg-content p { margin: 4px 0; }
.msg-content code {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: .9em;
  background: rgba(0,0,0,.06);
  padding: 1px 5px;
  border-radius: 4px;
}
.msg.user .msg-content code { background: rgba(255,255,255,.18); }
.msg-content pre {
  background: #0f172a; color: #e2e8f0;
  padding: 12px; border-radius: var(--radius);
  overflow-x: auto;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 13px;
}
.msg-content pre code { background: none; padding: 0; }
.msg-content blockquote {
  margin: 4px 0; padding: 4px 12px;
  border-left: 3px solid var(--c-border-strong);
  color: var(--c-text-soft);
}
.msg-content a { color: var(--c-primary); }
.msg-cites {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.msg-cites button {
  font-size: 11px; padding: 2px 8px;
  border: 1px solid var(--c-border-strong);
  background: var(--c-bg);
  border-radius: 999px;
  cursor: pointer;
  color: var(--c-text-soft);
}
.msg-cites button:hover { background: var(--c-bg-hover); color: var(--c-text); }
.msg.thinking .msg-content::after {
  content: "▍"; animation: blink 1s steps(2, start) infinite;
  margin-left: 2px;
  color: var(--c-text-soft);
}
@keyframes blink { to { visibility: hidden; } }
.msg.error .msg-content {
  background: #fef2f2; color: var(--c-danger); border-color: #fecaca;
}

/* === Empty state === */
#empty-state {
  position: absolute; inset: var(--header-h) 0 auto 0;
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.empty-inner { text-align: center; pointer-events: auto; }
.empty-inner h1 { margin: 0 0 8px; font-size: 28px; font-weight: 600; }
.empty-inner p { margin: 0 0 24px; color: var(--c-text-soft); }
.empty-inner .primary {
  padding: 10px 20px; font-size: 14px; font-weight: 500;
  border-radius: var(--radius);
  background: var(--c-primary); color: white; border: none;
  cursor: pointer;
}
.empty-inner .primary:hover { background: var(--c-primary-hover); }

/* === Composer === */
#composer {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--c-border);
  background: var(--c-bg);
}
#input {
  flex: 1;
  resize: none;
  padding: 10px 14px;
  border: 1px solid var(--c-border-strong);
  border-radius: var(--radius-lg);
  font: inherit;
  line-height: 1.5;
  background: var(--c-bg);
  color: var(--c-text);
  max-height: 160px;
  outline: none;
}
#input:focus { border-color: var(--c-primary); box-shadow: 0 0 0 3px rgba(37,99,235,.18); }
.composer-actions {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--c-text-soft);
}
.composer-actions button.primary {
  padding: 8px 16px; border: none;
  background: var(--c-primary); color: white;
  border-radius: var(--radius);
  cursor: pointer; font-weight: 500;
}
.composer-actions button.primary:hover { background: var(--c-primary-hover); }
.composer-actions button.primary:disabled { background: var(--c-border-strong); cursor: not-allowed; }
#stop {
  padding: 8px 16px; border: 1px solid var(--c-border-strong);
  background: var(--c-bg); color: var(--c-text);
  border-radius: var(--radius);
  cursor: pointer; font-weight: 500;
}

/* === Drawer === */
#drawer-backdrop {
  position: fixed; inset: 0; background: rgba(15,23,42,.32);
  z-index: 90;
}
#drawer {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: var(--drawer-w);
  background: var(--c-bg);
  box-shadow: var(--shadow-lg);
  display: flex; flex-direction: column;
  z-index: 100;
  animation: slide-in .15s ease-out;
}
@keyframes slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }
#drawer header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--c-border);
}
#drawer header h3 { margin: 0; font-size: 14px; font-weight: 600; }
#drawer-close {
  background: none; border: none; cursor: pointer;
  font-size: 22px; line-height: 1; padding: 0 6px;
  color: var(--c-text-soft);
}
#drawer-close:hover { color: var(--c-text); }
#drawer-body { overflow-y: auto; padding: 16px; flex: 1; }
.drawer-cite {
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--c-border);
}
.drawer-cite:last-child { border-bottom: none; }
.drawer-cite .cite-head { font-weight: 600; font-size: 13px; margin-bottom: 4px; }
.drawer-cite .cite-snippet { font-size: 12px; color: var(--c-text-soft); line-height: 1.5; }

/* === Toast === */
#toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  background: var(--c-text); color: white;
  padding: 10px 16px; border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  font-size: 13px;
  z-index: 200;
  animation: toast-in .2s ease-out;
}
@keyframes toast-in { from { opacity: 0; transform: translate(-50%, 8px); } to { opacity: 1; transform: translate(-50%, 0); } }

/* === Mobile (< 768px) === */
@media (max-width: 768px) {
  body { grid-template-columns: 1fr; }
  body:not(.sidebar-open) #sidebar { display: none; }
  body.sidebar-open { grid-template-columns: 1fr; }
  body.sidebar-open #sidebar {
    position: fixed; inset: 0 auto 0 0; width: 86vw; max-width: 320px;
    z-index: 95; box-shadow: var(--shadow-lg);
  }
  body.sidebar-open::after {
    content: ""; position: fixed; inset: 0; background: rgba(15,23,42,.4); z-index: 90;
  }
  .msg, .msg.user { max-width: 92%; }
  #topbar { padding: 0 12px; }
  #topbar h2 { font-size: 14px; max-width: 28ch; }
  #composer { padding: 8px 12px 12px; }
  #drawer { width: 92vw; max-width: 360px; }
}
```

- [ ] **Step 3: Verify HTML & CSS load**

```bash
bash scripts/run.sh &  # if not already running
sleep 3
curl -s http://localhost:8000/ | head -40
curl -sI http://localhost:8000/style.css | head -3
curl -s http://localhost:8000/app.js?v=5 | head -3
```
Expected: HTML contains `id="sidebar"`, `id="chat-list"`, `id="messages"`, `id="empty-state"`, `id="drawer"`. CSS responds 200 with `Cache-Control: no-store`. app.js?v=5 returns 200.

- [ ] **Step 4: Commit skeleton**

```bash
git add web/index.html web/style.css
git commit -m "feat(web): new HTML shell + modern CSS for sidebar/chat layout

Lays out the new structure: collapsible sidebar with grouped chat
list, topbar with title + actions, message area with markdown
styling, citation drawer, toast, and mobile breakpoint. JS logic
follows in subsequent tasks.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Frontend `app.js` — store, utils, wsClient, markdown

**Files:**
- Rewrite: `web/app.js`
- (single file rewrite, but the review gate treats this as one focused PR)

**Interfaces (called by Task 5 modules; defined here):**

```js
// utils
uuidv4() -> string
escapeHtml(s: string) -> string
formatRelativeTime(ts: number) -> string          // "刚刚" / "5 分钟前" / "HH:MM"
autoTitle(text: string) -> string                  // first 24 chars
toast(text: string) -> void                        // bottom toast 2.5s

// store
store.state        // { version: 1, activeId: string, chats: Chat[] }
store.load()       // -> state, mutates in place
store.save()       // -> void
store.mutate(fn)   // fn(state); store.save(); listeners notified

// wsClient
wsClient.connect(history: Array<{role,content}>, handlers: {
  onToken: (s: string)=>void,
  onCitation: (cites: Citation[])=>void,
  onDone: ()=>void,
  onError: (msg: string)=>void,
}) -> { abort: ()=>void }

// markdown
md(text: string) -> string   // safe HTML
```

- [ ] **Step 1: Replace `web/app.js` with a working shell that only implements utils + store + wsClient + markdown + a no-op `boot()`**

This step lands the foundation; the UI is invisible until Task 5 wires it up. (The previous single-session app.js remains uninstalled behaviorally — but its old functions are gone.)

Replace the whole file with:

```js
"use strict";
// ============================================================================
// AI 辅导员 — multi-session client. All persistence is in localStorage; the
// server is stateless and receives the full history on every WS frame.
// ============================================================================

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// ---------- Constants & utils ----------
const STORAGE_KEY = "counselor:state";
const STATE_VERSION = 1;
const MAX_TITLE_LEN = 24;
const MAX_MESSAGE_CHARS = 4000;
const MAX_HISTORY_CHARS = 4000 * 20;
const MAX_TITLE_PREFIX = (n) => `${n}/4000`;

function uuidv4() {
  if (typeof crypto !== "undefined") {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    if (typeof crypto.getRandomValues === "function") {
      const b = crypto.getRandomValues(new Uint8Array(16));
      b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
      const h = []; for (let i = 0; i < 16; i++) h.push(b[i].toString(16).padStart(2, "0"));
      return `${h.slice(0,4).join("")}-${h.slice(4,6).join("")}-${h.slice(6,8).join("")}-${h.slice(8,10).join("")}-${h.slice(10,16).join("")}`;
    }
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function formatRelativeTime(ts) {
  const diff = Date.now() - ts;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  const d = new Date(ts);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(ts); day.setHours(0, 0, 0, 0);
  if (day.getTime() === today.getTime()) return d.toTimeString().slice(0, 5);
  if (day.getTime() === today.getTime() - 86_400_000) return "昨天";
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function autoTitle(text) {
  const t = String(text || "").trim().replace(/\s+/g, " ");
  if (!t) return "新会话";
  return t.length > MAX_TITLE_LEN ? t.slice(0, MAX_TITLE_LEN) + "…" : t;
}

let _toastTimer = null;
function toast(text) {
  const el = $("#toast"); if (!el) return;
  const t = $("#toast-text"); if (t) t.textContent = text;
  el.hidden = false;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.hidden = true; }, 2500);
}

async function fetchWithTimeout(url, options = {}, ms = 3000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try { return await fetch(url, { ...options, signal: ctrl.signal }); }
  finally { clearTimeout(t); }
}

// ---------- Store ----------
function blankChat() {
  const now = Date.now();
  return { id: uuidv4(), title: "新会话", createdAt: now, updatedAt: now, messages: [] };
}

function blankState() {
  const c = blankChat();
  return { version: STATE_VERSION, activeId: c.id, chats: [c] };
}

const store = {
  state: blankState(),
  _listeners: [],
  _loadFailed: false,
  load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) { this.state = blankState(); return this.state; }
      const parsed = JSON.parse(raw);
      if (parsed && parsed.version === STATE_VERSION && Array.isArray(parsed.chats) && parsed.chats.length > 0) {
        // Validate each chat has the required fields; drop broken ones.
        parsed.chats = parsed.chats.filter((c) =>
          c && typeof c.id === "string" && Array.isArray(c.messages) &&
          typeof c.title === "string" && typeof c.createdAt === "number"
        );
        if (parsed.chats.length === 0) {
          const fresh = blankChat();
          parsed.chats = [fresh]; parsed.activeId = fresh.id;
        }
        if (!parsed.chats.find((c) => c.id === parsed.activeId)) parsed.activeId = parsed.chats[0].id;
        this.state = parsed;
      } else {
        this.state = blankState();
      }
    } catch (e) {
      console.warn("[store] load failed; using in-memory only:", e);
      this._loadFailed = true;
      this.state = blankState();
    }
    return this.state;
  },
  save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.state));
    } catch (e) {
      console.warn("[store] save failed:", e);
      toast("存储空间不足，请删除旧会话");
    }
  },
  mutate(fn) {
    fn(this.state);
    this.save();
    for (const l of this._listeners) l(this.state);
  },
  onChange(fn) { this._listeners.push(fn); return () => { this._listeners = this._listeners.filter((l) => l !== fn); }; },
  active() { return this.state.chats.find((c) => c.id === this.state.activeId) || this.state.chats[0]; },
};

// ---------- WS client ----------
const wsClient = {
  _ws: null,
  connect(history, handlers) {
    // Abort any existing connection first.
    if (this._ws) { try { this._ws.close(); } catch {} this._ws = null; }
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/ws/chat`;
    const sessionId = store.active()?.id || uuidv4();
    const ws = new WebSocket(url);
    this._ws = ws;
    const sendTimer = setTimeout(() => {
      try { ws.close(); } catch {}
      handlers.onError("连接超时（90s）");
    }, 90_000);
    ws.onopen = () => {
      try {
        ws.send(JSON.stringify({ session_id: sessionId, history }));
      } catch (e) {
        handlers.onError("发送失败：" + e);
        try { ws.close(); } catch {}
      }
    };
    ws.onmessage = (ev) => {
      let payload; try { payload = JSON.parse(ev.data); } catch { return; }
      if (payload.event === "token") handlers.onToken(payload.data || "");
      else if (payload.event === "citation") handlers.onCitation(payload.data || []);
      else if (payload.event === "done") { clearTimeout(sendTimer); handlers.onDone(); }
      else if (payload.event === "error") { clearTimeout(sendTimer); handlers.onError(payload.data || "未知错误"); }
    };
    ws.onerror = () => { clearTimeout(sendTimer); handlers.onError("WebSocket 连接失败"); };
    ws.onclose = () => { clearTimeout(sendTimer); if (this._ws === ws) this._ws = null; };
    return { abort: () => { try { ws.close(); } catch {} } };
  },
};

// ---------- Markdown (minimal safe renderer) ----------
function md(text) {
  if (!text) return "";
  // 1. Escape first.
  let s = escapeHtml(text);
  // 2. Fenced code blocks ```lang\n...\n```
  s = s.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${escapeHtml(lang)}">${code}</code></pre>`);
  // 3. Inline code `code`
  s = s.replace(/`([^`\n]+)`/g, (_, code) => `<code>${code}</code>`);
  // 4. Bold **text**
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  // 5. Links [text](url) — strip dangerous protocols.
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, t, u) => {
    const safe = /^(https?:|mailto:|#|\/)/i.test(u.trim()) ? u : "#";
    return `<a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${t}</a>`;
  });
  // 6. Block-level: split on blank lines, then per-line scan.
  const blocks = s.split(/\n{2,}/);
  return blocks.map((block) => {
    const lines = block.split("\n");
    // Headings
    if (lines.every((l) => /^### /.test(l))) return "<h3>" + lines.map((l) => l.slice(4)).join("<br>") + "</h3>";
    if (lines.every((l) => /^## /.test(l))) return "<h2>" + lines.map((l) => l.slice(3)).join("<br>") + "</h2>";
    if (lines.every((l) => /^# /.test(l))) return "<h1>" + lines.map((l) => l.slice(2)).join("<br>") + "</h1>";
    // Unordered list
    if (lines.every((l) => /^[-*] /.test(l))) {
      return "<ul>" + lines.map((l) => `<li>${l.slice(2)}</li>`).join("") + "</ul>";
    }
    // Ordered list
    if (lines.every((l) => /^\d+\. /.test(l))) {
      return "<ol>" + lines.map((l) => `<li>${l.replace(/^\d+\. /, "")}</li>`).join("") + "</ol>";
    }
    // Blockquote
    if (lines.every((l) => /^> /.test(l))) return "<blockquote>" + lines.map((l) => l.slice(2)).join("<br>") + "</blockquote>";
    // Paragraph with inline newlines → <br>
    return "<p>" + lines.join("<br>") + "</p>";
  }).join("");
}

// ---------- Boot (placeholder — Task 5 wires the rest) ----------
function boot() {
  store.load();
  if (store._loadFailed) toast("数据无法从本地加载，仅本次会话可用");
}

boot();
```

- [ ] **Step 2: Smoke test in browser console**

Open `http://localhost:8000`, DevTools console, evaluate:

```js
// should return a non-empty string
JSON.parse(localStorage.getItem("counselor:state") || "{}").activeId
md("**hello** `code`\n\n- a\n- b")
```

Expected: First expression returns a UUID. Second returns HTML containing `<strong>hello</strong>`, `<code>code</code>`, `<ul><li>a</li><li>b</li></ul>`.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): utils + store + wsClient + markdown renderer

Foundation for the new multi-session UI. Persists state to
localStorage['counselor:state'] and provides a minimal safe markdown
renderer. UI wiring lands in the next commit.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Frontend `app.js` — renderers, actions, input, sidebar, boot

**Files:**
- Modify: `web/app.js` (append the rendering / action / glue sections; replace `boot()` placeholder)

**No new IDs beyond those already declared in Task 3's HTML.** No new third-party deps.

- [ ] **Step 1: Append the renderer / actions / glue sections and replace `boot()`**

Open `web/app.js`. Delete the existing `// ---------- Boot (placeholder — Task 5 wires the rest) ----------` block and everything below it. Then append the implementation below. (Keep everything above it — utils, store, wsClient, markdown.)

```js
// ============================================================================
// Renderer
// ============================================================================
const renderer = {
  init() {
    store.onChange(() => this.renderAll());
  },
  renderAll() {
    this.renderSidebar();
    this.renderChat();
  },

  // -- Sidebar --
  renderSidebar() {
    const list = $("#chat-list"); if (!list) return;
    const chats = [...store.state.chats].sort((a, b) => b.updatedAt - a.updatedAt);
    // Group by updatedAt bucket.
    const today0 = new Date(); today0.setHours(0, 0, 0, 0);
    const yesterday0 = new Date(today0.getTime() - 86_400_000);
    const week0 = new Date(today0.getTime() - 6 * 86_400_000);
    const groups = { 今天: [], 昨天: [], 本周: [], 更早: [] };
    for (const c of chats) {
      const t = new Date(c.updatedAt); t.setHours(0, 0, 0, 0);
      if (t.getTime() >= today0.getTime()) groups["今天"].push(c);
      else if (t.getTime() >= yesterday0.getTime()) groups["昨天"].push(c);
      else if (t.getTime() >= week0.getTime()) groups["本周"].push(c);
      else groups["更早"].push(c);
    }
    const frag = document.createDocumentFragment();
    for (const [name, arr] of Object.entries(groups)) {
      if (arr.length === 0) continue;
      const h = document.createElement("div");
      h.className = "chat-group-title"; h.textContent = name;
      frag.appendChild(h);
      for (const c of arr) {
        const item = document.createElement("div");
        item.className = "chat-item" + (c.id === store.state.activeId ? " active" : "");
        item.dataset.id = c.id;
        const t = document.createElement("span");
        t.className = "chat-title-text"; t.textContent = c.title;
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "chat-menu-btn"; btn.textContent = "⋯";
        btn.title = "更多";
        btn.dataset.act = "menu";
        item.appendChild(t); item.appendChild(btn);
        frag.appendChild(item);
      }
    }
    list.replaceChildren(frag);
  },

  // -- Topbar --
  renderTopbar() {
    const titleEl = $("#chat-title"); if (!titleEl) return;
    titleEl.textContent = store.active()?.title || "新会话";
  },

  // -- Chat --
  renderChat() {
    const msgsEl = $("#messages"); const emptyEl = $("#empty-state");
    if (!msgsEl || !emptyEl) return;
    this.renderTopbar();
    const chat = store.active();
    if (!chat || chat.messages.length === 0) {
      msgsEl.replaceChildren();
      emptyEl.hidden = false;
      return;
    }
    emptyEl.hidden = true;
    const frag = document.createDocumentFragment();
    const tpl = $("#message-template");
    for (const m of chat.messages) {
      const node = tpl.content.firstElementChild.cloneNode(true);
      this._fillMessage(node, m);
      frag.appendChild(node);
    }
    msgsEl.replaceChildren(frag);
    msgsEl.scrollTop = msgsEl.scrollHeight;
  },
  _fillMessage(node, m) {
    node.classList.add(m.role);
    const content = $(".msg-content", node);
    if (m.role === "assistant") content.innerHTML = md(m.content || "");
    else content.textContent = m.content || "";
    const cites = $(".msg-cites", node);
    if (m.role === "assistant" && Array.isArray(m.citations) && m.citations.length > 0) {
      cites.hidden = false;
      cites.replaceChildren(...m.citations.map((c, i) => {
        const b = document.createElement("button");
        b.type = "button"; b.textContent = `引 ${i + 1}`;
        b.dataset.citeIdx = String(i);
        return b;
      }));
    }
  },

  // -- Live assistant bubble (during streaming) --
  appendLiveBubble() {
    const msgsEl = $("#messages"); const tpl = $("#message-template");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.classList.add("assistant", "thinking");
    node.dataset.live = "1";
    $(".msg-content", node).textContent = "";
    msgsEl.appendChild(node);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    return {
      setToken: (s) => {
        const c = $(".msg-content", node);
        c.textContent = s;
        msgsEl.scrollTop = msgsEl.scrollHeight;
      },
      setCitations: (cites) => {
        const citesEl = $(".msg-cites", node);
        if (!cites || cites.length === 0) { citesEl.hidden = true; return; }
        citesEl.hidden = false;
        citesEl.replaceChildren(...cites.map((c, i) => {
          const b = document.createElement("button");
          b.type = "button"; b.textContent = `引 ${i + 1}`;
          b.dataset.citeIdx = String(i); b.dataset.live = "1";
          return b;
        }));
      },
      finish: () => {
        node.classList.remove("thinking");
        const live = $$("[data-live='1']", node); live.forEach((el) => delete el.dataset.live);
      },
      showError: (msg) => {
        node.classList.remove("thinking"); node.classList.add("error");
        $(".msg-content", node).textContent = "（出错了）" + msg;
        const live = $$("[data-live='1']", node); live.forEach((el) => delete el.dataset.live);
      },
    };
  },
};

// ============================================================================
// Chat actions
// ============================================================================
const chatActions = {
  create() {
    store.mutate((s) => {
      const c = blankChat();
      s.chats.push(c); s.activeId = c.id;
    });
  },
  switchTo(id) {
    if (!store.state.chats.find((c) => c.id === id)) return;
    store.mutate((s) => { s.activeId = id; });
  },
  rename(id, newTitle) {
    const t = String(newTitle || "").trim();
    if (!t) return;
    store.mutate((s) => {
      const c = s.chats.find((x) => x.id === id); if (c) { c.title = t; c.updatedAt = Date.now(); }
    });
  },
  remove(id) {
    store.mutate((s) => {
      s.chats = s.chats.filter((c) => c.id !== id);
      if (s.chats.length === 0) { const c = blankChat(); s.chats.push(c); }
      if (id === s.activeId) s.activeId = s.chats[0].id;
    });
  },
  clearAll() {
    store.mutate((s) => {
      const c = blankChat();
      s.chats = [c]; s.activeId = c.id;
    });
  },
  async send(text) {
    const t = String(text || "").trim();
    if (!t || t.length > MAX_MESSAGE_CHARS) return;
    const chat = store.active(); if (!chat) return;
    // Push user message + auto-title if needed.
    store.mutate((s) => {
      const c = s.chats.find((x) => x.id === s.activeId);
      c.messages.push({ role: "user", content: t, ts: Date.now() });
      c.updatedAt = Date.now();
      if (c.title === "新会话") c.title = autoTitle(t);
    });
    renderer.renderChat();
    // Build history from current chat (drop tool messages).
    const history = chat.messages
      .filter((m) => m.role !== "tool")
      .map((m) => ({ role: m.role, content: m.content || "" }));
    const live = renderer.appendLiveBubble();
    let buffer = ""; let cites = [];
    wsClient.connect(history, {
      onToken: (chunk) => { buffer += chunk; live.setToken(buffer); },
      onCitation: (c) => { cites = c; live.setCitations(c); },
      onDone: () => {
        live.finish();
        store.mutate((s) => {
          const c = s.chats.find((x) => x.id === s.activeId);
          c.messages.push({ role: "assistant", content: buffer, citations: cites, ts: Date.now() });
          c.updatedAt = Date.now();
        });
      },
      onError: (msg) => {
        live.showError(msg);
        // Don't push the assistant message — user can retry.
      },
    });
  },
};

// ============================================================================
// Controller glue
// ============================================================================
const inputCtl = {
  init() {
    const input = $("#input"); const send = $("#send"); const count = $("#char-count");
    if (!input || !send || !count) return;
    const submit = () => {
      const v = input.value;
      if (!v.trim()) return;
      input.value = ""; count.textContent = "0"; input.style.height = "auto";
      chatActions.send(v);
    };
    const autoSize = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; };
    input.addEventListener("input", () => { count.textContent = String(input.value.length); autoSize(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    });
    send.addEventListener("click", submit);
  },
};

const sidebarCtl = {
  init() {
    const list = $("#chat-list"); const toggle = $("#sidebar-toggle");
    const toggleInline = $("#sidebar-toggle-inline");
    const newBtn = $("#new-chat-btn");
    const setCollapsed = (collapsed) => {
      document.body.classList.toggle("sidebar-collapsed", collapsed);
      try { localStorage.setItem("counselor:sidebar-collapsed", collapsed ? "1" : "0"); } catch {}
    };
    if (toggle) toggle.addEventListener("click", () => {
      const collapsed = !document.body.classList.contains("sidebar-collapsed");
      setCollapsed(collapsed);
    });
    if (toggleInline) toggleInline.addEventListener("click", () => setCollapsed(false));
    if (newBtn) newBtn.addEventListener("click", () => { chatActions.create(); });
    if (list) list.addEventListener("click", (e) => {
      const item = e.target.closest(".chat-item"); if (!item) return;
      const id = item.dataset.id;
      if (e.target.dataset.act === "menu") {
        const rect = item.getBoundingClientRect();
        openContextMenu(id, rect.left, rect.bottom);
        return;
      }
      chatActions.switchTo(id);
    });
    // Restore collapsed state.
    try {
      if (localStorage.getItem("counselor:sidebar-collapsed") === "1") setCollapsed(true);
    } catch {}
  },
};

const topbarCtl = {
  init() {
    const titleEl = $("#chat-title"); const inputEl = $("#chat-title-input");
    const commit = () => {
      const newTitle = inputEl.value.trim();
      inputEl.hidden = true; titleEl.hidden = false;
      if (newTitle) chatActions.rename(store.active().id, newTitle);
      else renderer.renderTopbar();
    };
    const cancel = () => { inputEl.hidden = true; titleEl.hidden = false; };
    const beginEdit = () => {
      inputEl.value = store.active().title;
      inputEl.hidden = false; titleEl.hidden = true;
      inputEl.focus(); inputEl.select();
    };
    if (titleEl) titleEl.addEventListener("click", beginEdit);
    if (titleEl) titleEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); beginEdit(); } });
    if (inputEl) {
      inputEl.addEventListener("blur", commit);
      inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); commit(); }
        else if (e.key === "Escape") { e.preventDefault(); cancel(); }
      });
    }
    // Actions menu
    const btn = $("#chat-actions-btn"); const menu = $("#chat-actions-menu");
    if (btn && menu) {
      btn.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; });
      document.addEventListener("click", () => { menu.hidden = true; });
      menu.addEventListener("click", (e) => {
        const act = e.target.dataset.act; if (!act) return;
        menu.hidden = true;
        if (act === "rename") { beginEdit(); }
        else if (act === "delete") {
          if (confirm("删除当前会话？此操作不可撤销。")) chatActions.remove(store.active().id);
        }
        else if (act === "clear-all") {
          if (confirm("清空全部会话？此操作不可撤销。")) chatActions.clearAll();
        }
      });
    }
    // Reindex
    const reindexBtn = $("#reindex");
    if (reindexBtn) reindexBtn.addEventListener("click", async () => {
      reindexBtn.disabled = true; reindexBtn.textContent = "处理中…";
      try {
        const r = await fetchWithTimeout("/api/ingest", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ force: false }),
        }, 30000);
        const data = await r.json();
        toast(`索引完成：新增 ${data.added}，跳过 ${data.skipped}，失败 ${data.failed.length}`);
        refreshHealth();
      } catch (e) { toast("入索引失败：" + e); }
      finally { reindexBtn.disabled = false; reindexBtn.textContent = "重建索引"; }
    });
  },
};

// Citation drawer
const drawerCtl = {
  init() {
    const drawer = $("#drawer"); const body = $("#drawer-body"); const close = $("#drawer-close"); const backdrop = $("#drawer-backdrop");
    const closeDrawer = () => { drawer.hidden = true; backdrop.hidden = true; body.replaceChildren(); };
    if (close) close.addEventListener("click", closeDrawer);
    if (backdrop) backdrop.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !drawer.hidden) closeDrawer(); });
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".msg-cites button[data-cite-idx]"); if (!btn) return;
      const msgNode = btn.closest(".msg"); const idx = Number(btn.dataset.citeIdx);
      const chat = store.active(); const msg = chat?.messages.find((m) => m === _currentLiveMsg || true);
      // Find the message that contains this button (rendered or live).
      let m = chat?.messages.find((x) => x.role === "assistant" && Array.isArray(x.citations) && x.citations[idx]);
      if (!m) {
        const liveNode = document.querySelector(".msg.assistant.thinking, .msg.assistant");
        const liveCites = liveNode ? $$(".msg-cites button[data-cite-idx]", liveNode) : [];
        const liveIdx = liveCites.indexOf(btn);
        if (liveIdx >= 0) m = _liveCitations[liveIdx] && { citations: _liveCitations };
      }
      if (!m || !m.citations || !m.citations[idx]) return;
      const c = m.citations[idx];
      body.replaceChildren();
      const card = document.createElement("div");
      card.className = "drawer-cite";
      const head = document.createElement("div"); head.className = "cite-head"; head.textContent = `《${c.filename}》 第 ${c.page} 页`;
      const snip = document.createElement("div"); snip.className = "cite-snippet"; snip.textContent = c.snippet || "";
      card.appendChild(head); card.appendChild(snip); body.appendChild(card);
      drawer.hidden = false; backdrop.hidden = false;
    });
  },
};
// Track live citation array so drawer can resolve before store commit.
const _liveCitations = [];

// Empty state new button
const emptyCtl = {
  init() {
    const btn = $("#empty-state-new"); if (btn) btn.addEventListener("click", () => chatActions.create());
  },
};

// Context menu for chat items (simple confirm-based; reuse window.confirm to avoid new UI)
function openContextMenu(id, x, y) {
  const c = store.state.chats.find((x) => x.id === id); if (!c) return;
  const choice = prompt(`操作「${c.title}」：\n1. 重命名\n2. 删除\n输入 1 或 2：`);
  if (choice === "1") {
    const t = prompt("新标题：", c.title);
    if (t && t.trim()) chatActions.rename(id, t.trim());
  } else if (choice === "2") {
    if (confirm("删除这个会话？")) chatActions.remove(id);
  }
}

// ---------- Health probe ----------
let _healthDot = null, _healthText = null;
async function refreshHealth() {
  if (!_healthDot) { _healthDot = $("#status-dot"); _healthText = $("#status-text"); }
  try {
    const r = await fetchWithTimeout("/api/health", {}, 3000);
    const data = await r.json();
    const ok = data.status === "ok";
    _healthDot.classList.toggle("ok", ok);
    _healthDot.classList.toggle("degraded", !ok);
    _healthText.textContent = ok ? "在线" : (data.llm ? "索引未建立" : "模型未连接");
  } catch (e) {
    _healthDot.classList.remove("ok"); _healthDot.classList.add("degraded");
    _healthText.textContent = e.name === "AbortError" ? "连接超时" : "无法连接后端";
  }
}

// ---------- Boot ----------
function boot() {
  store.load();
  if (store._loadFailed) toast("数据无法从本地加载，仅本次会话可用");
  renderer.init();
  sidebarCtl.init();
  topbarCtl.init();
  inputCtl.init();
  drawerCtl.init();
  emptyCtl.init();
  renderer.renderAll();
  refreshHealth();
  setInterval(refreshHealth, 30000);
}

boot();
```

- [ ] **Step 2: Smoke test in browser**

Open `http://localhost:8000`, verify:
- Left sidebar shows one entry "新会话" under "今天".
- Topbar shows "新会话".
- Empty state is hidden.
- Click `＋ 新会话` → new entry appears, active switches.
- Click first entry → active switches back.
- Send a message → assistant bubble appears + reply text streams in.
- F5 (refresh) → all chats persist.
- Open DevTools → `localStorage["counselor:state"]` contains both chats with messages.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): full multi-session UI wiring

Sidebar with grouped chat list, topbar with rename + actions menu,
markdown-rendered messages with citation chips, drawer for citation
snippets, empty state, mobile responsive. State persists to
localStorage; backend is fully stateless (server-side history removed).

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Update `test_api.py` for the new frontend

**Files:**
- Modify: `tests/test_api.py` (rewrite frontend-assertion tests for the new structure)

**Interfaces:** No code change; only assertion rewrites.

- [ ] **Step 1: Inspect existing assertions**

Read `tests/test_api.py` and identify which existing assertions test the old single-session UI:

- `test_frontend_health_requests_have_timeouts` — tests old `app.js` strings; will fail after rewrite.
- `test_frontend_script_is_cache_busted` — tests `v=4`; needs `v=5`.
- `test_frontend_clears_citations_on_new_send` — tests an old pattern; replace.
- `test_static_files_have_no_store_cache_header` — keep as-is.

- [ ] **Step 2: Replace those four tests with the new ones**

Replace the four tests. The replacement is:

```python
def test_static_files_have_no_store_cache_header(client):
    """前端静态文件应带 ``Cache-Control: no-store``，强制浏览器每次拿最新
    版本，避免改了 app.js 但浏览器仍跑老 JS 的问题。"""
    for path in ("/", "/app.js", "/style.css"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        assert r.headers.get("cache-control") == "no-store", (
            f"{path} 缺少 Cache-Control: no-store 头；浏览器会缓存旧 JS 导致 "
            f"改前端代码后看不到效果"
        )


def test_frontend_uses_localstorage_for_history(client):
    app_js = client.get("/app.js").text
    assert 'localStorage.getItem("counselor:state")' in app_js
    assert 'localStorage.setItem("counselor:state"' in app_js


def test_frontend_sends_full_history_per_request(client):
    app_js = client.get("/app.js").text
    # `history` field is sent in the WS open frame.
    assert '"history"' in app_js or "'history'" in app_js


def test_frontend_has_sidebar_and_toggle(client):
    html = client.get("/").text
    assert 'id="sidebar"' in html
    assert 'id="sidebar-toggle"' in html
    assert 'id="chat-list"' in html
    assert 'id="new-chat-btn"' in html


def test_frontend_cache_bust_is_v5(client):
    html = client.get("/").text
    assert '<script src="app.js?v=5"></script>' in html


def test_frontend_includes_citation_drawer(client):
    html = client.get("/").text
    assert 'id="drawer"' in html
    assert 'id="drawer-body"' in html


def test_frontend_drops_old_session_storage(client):
    """旧版单一 session_id 的代码应已彻底移除（除了 UUID 生成函数里出现的字符串）。"""
    app_js = client.get("/app.js").text
    # 不再出现 localStorage.getItem("session_id") / setItem("session_id")
    assert 'localStorage.getItem("session_id")' not in app_js
    assert 'localStorage.setItem("session_id"' not in app_js
```

Keep `test_health_returns_struct` and `test_ingest_runs_with_empty_corpus` unchanged.

- [ ] **Step 3: Run all tests**

```bash
OFFLINE=1 uv run --extra dev pytest -q
```
Expected: 39 (old baseline) + 7 (test_chat_history.py) + 7 (rewritten test_api.py frontend assertions) − 4 (removed) = **49 passed**, 2 skipped.

If any assertion fails, read the diff and fix `app.js` or `index.html` accordingly — do NOT loosen the assertion.

- [ ] **Step 4: Commit**

```bash
git add tests/test_api.py
git commit -m "test(api): rewrite frontend assertions for multi-session UI

Verifies localStorage usage, history WS field, sidebar/topbar/drawer
elements, cache-bust bump, and removal of old single-session_id code.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: README + CLAUDE.md updates

**Files:**
- Modify: `README.md` (replace the "会话管理" / "重置会话" / usage section)
- Modify: `CLAUDE.md` (drop SqliteSaver rows; add new architecture summary)

- [ ] **Step 1: Update README**

Read the current README, find the usage / "Web UI" section, and rewrite it to describe:
- Multi-session sidebar: create, switch, rename (click title), delete (⋯ menu)
- Persistence: client-only (localStorage); restart server loses nothing client-side
- Markdown rendering + citation chips
- Mobile responsive

Replace only that section; do not touch unrelated install / run / test sections.

- [ ] **Step 2: Update CLAUDE.md**

- Remove the "SqliteSaver" rows from the "Known Pitfalls" table.
- Replace the LangGraph Agent section paragraph that mentions `SqliteSaver` and `data/checkpoints.db`.
- Add a "Frontend" subsection describing: vanilla JS in `web/`, all state in `localStorage["counselor:state"]`, ChatGPT-style sidebar layout, cache-bust `?v=N`.
- Bump the WS protocol description from "single message per session_id" to "full history per request".

- [ ] **Step 3: Re-run full test suite as final sanity check**

```bash
OFFLINE=1 uv run --extra dev pytest -q
```
Expected: 49 passed, 2 skipped.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: README + CLAUDE.md reflect stateless backend + multi-session UI

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Manual smoke + final verification

**Files:** none — pure verification.

- [ ] **Step 1: Run full automated suite**

```bash
OFFLINE=1 uv run --extra dev pytest -q
```
Expected: green. Note exact count for the commit message.

- [ ] **Step 2: Restart server and do a browser smoke**

```bash
pkill -f "uvicorn app.main" || true
rm -f data/checkpoints.db
bash scripts/run.sh &
sleep 4
curl -s http://localhost:8000/api/health
```

Open `http://localhost:8000` in a browser. Walk through:

1. See left sidebar with one "新会话" entry.
2. Type "你好" → assistant bubble appears with reply.
3. Click `＋ 新会话` → new chat appears in sidebar, chat area clears.
4. Type "概率公式有哪些" → reply + citation chips appear.
5. Click `[引 1]` → drawer slides in from right showing snippet.
6. Click first chat in sidebar → original "你好" conversation restored.
7. F5 (refresh) → all chats persist.
8. Click `⋯` on a chat → "重命名" → type new title → confirm.
9. Click `⋯` → "删除会话" → confirm → that chat gone, active switches.
10. Click "清空全部会话" → only one empty "新会话" remains.
11. DevTools → `localStorage["counselor:state"]` shows current shape.
12. Stop server (`pkill -f "uvicorn app.main"`); restart; refresh → client data still there (server lost nothing because it had nothing to lose).

- [ ] **Step 3: Mobile responsive check**

In browser DevTools → toggle device toolbar → iPhone SE (375×667):
- Sidebar is hidden by default.
- Tap `≡` in topbar → sidebar overlays chat area with backdrop.
- Tap a chat → sidebar closes, chat opens.
- Drawer takes ~92vw on mobile.

- [ ] **Step 4: Final commit (changelog note if any drift surfaced)**

If no code changes were needed, no commit. If anything surfaced during smoke, fix it and commit:

```bash
git add -A
git commit -m "fix(web): <what was wrong> (surfaced during manual smoke)"
```

- [ ] **Step 5: Print summary**

Print to the terminal:

```
## Summary

- Backend: stateless; receives full history per WS frame.
- Frontend: multi-session, localStorage-only, ChatGPT-style sidebar.
- Tests: 49 passed, 2 skipped.
- Files touched: app/routes_chat.py, agent/graph.py, storage/paths.py,
  scripts/run.sh, web/{index.html, style.css, app.js},
  tests/{conftest.py, test_api.py, test_chat_history.py},
  README.md, CLAUDE.md.
```

---

## Self-Review Notes

- **Spec coverage:**
  - §1 architecture & boundaries — Task 1 (handler) + Task 2 (graph) + Task 5 (boot).
  - §2 localStorage schema — Task 4 (store) implements exact `version`/`activeId`/`chats`/`messages`/`citations` shape; autoTitle function included.
  - §3 WS protocol & backend — Task 1.
  - §3.3 SqliteSaver removal — Task 2.
  - §4 UI layout — Task 3 (HTML/CSS), Task 5 (glue).
  - §4.2 collapsible sidebar — `sidebarCtl` toggles `body.sidebar-collapsed`; state persisted to `localStorage["counselor:sidebar-collapsed"]`.
  - §4.3 markdown — Task 4 `md()`.
  - §4.4 citation drawer — Task 5 `drawerCtl`.
  - §4.5 mobile — Task 3 `@media (max-width: 768px)`.
  - §5 module split — Task 4 (utils/store/wsClient/markdown) + Task 5 (renderer/actions/controllers).
  - §5.3 flows (new chat / switch / delete / rename / send) — Task 5 `chatActions`.
  - §6 testing — Task 1 (backend) + Task 6 (frontend).
  - §7 error handling — Task 5 (`_loadFailed` toast, store save try/catch, WS error path).
  - §8 implementation steps — these 8 tasks.
  - §10 acceptance criteria — Task 8 verification.

- **Placeholder scan:** No "TBD"/"TODO"/"implement later" in any task body. All code shown is final (only minor edits during execution should be needed).

- **Type consistency:** `Citation` shape `{filename, page, snippet}` is the same in `app.js` (UI consumes) and `app/routes_chat.py` (backend emits via `to_citations`). `Chat.messages[]` items have `role` ∈ `{"user","assistant","tool"}`. `store.active()` returns the chat object whose `id === store.state.activeId`. `chatActions.send(text)` returns Promise but is not awaited anywhere (fire-and-forget); error path is via the WS handlers.