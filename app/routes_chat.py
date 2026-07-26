# app/routes_chat.py
from __future__ import annotations

import json
import re
import traceback
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from .admin.settings import get_effective_settings
from .schemas import ErrorEvent
from agent.graph import build_graph
from llm.client import get_llm
from rag.citations import to_citations
from rag.retriever import get_retriever


router = APIRouter()


# Per-history-item content cap (chars). Combined total cap is enforced separately.
_MAX_ITEM_CHARS = 4000
# Combined history content cap (four maximum-length items).
_MAX_HISTORY_CHARS = 4000 * 4  # 16 000 chars


_VALID_ROLES = {"user", "assistant"}


# Native chain-of-thought / reasoning delimiters used by Qwen, DeepSeek,
# MiniMax, Anthropic-style and various OSS models. Each pair is matched
# non-greedy with DOTALL (cross-line). Missing close tag is NOT deleted
# (regex requires a pair) so we never silently lose content. Add new pairs
# here as new model families appear.
_REASONING_PAIRS: tuple[tuple[str, str], ...] = (
    ("<think>", "</think>"),
    ("<reasoning>", "</reasoning>"),
    ("<|reasoning|>", "</|reasoning|>"),
    ("<reflection>", "</reflection>"),
    ("<analysis>", "</analysis>"),
    ("<scratchpad>", "</scratchpad>"),
    ("<thinking>", "</thinking>"),
    ("<plan>", "</plan>"),
)

_REASONING_RE = re.compile(
    "|".join(re.escape(o) + r".*?" + re.escape(c) for o, c in _REASONING_PAIRS),
    re.DOTALL,
)


def _strip_reasoning(content: str, *, show: bool) -> str:
    """Remove native CoT / reasoning blocks from a model's reply.

    `show=False` (default) strips all configured reasoning delimiters and
    surrounding whitespace, so ordinary users never see the model's internal
    monologue. `show=True` returns the content unchanged — used when the WS
    caller passes `show_reasoning: true` for admin debugging.
    """
    if show:
        return content
    return _REASONING_RE.sub("", content).strip()


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
        # OR semantics: WS payload flag (per-session, e.g. ?debug=reasoning
        # URL param) OR admin settings debug.show_reasoning (global toggle).
        ws_show = bool(payload.get("show_reasoning", False))
        admin_show = bool(
            get_effective_settings().get("debug", {}).get("show_reasoning", False)
        )
        show_reasoning = ws_show or admin_show

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
                ai_content_raw = ai_messages[-1].content or ""
                ai_content = _strip_reasoning(ai_content_raw, show=show_reasoning)
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
