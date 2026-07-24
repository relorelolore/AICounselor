# app/routes_chat.py
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .schemas import ErrorEvent
from agent.graph import build_graph
from llm.client import get_llm
from rag.retriever import get_retriever
from storage.paths import CHECKPOINT_DB


router = APIRouter()


def _validate_session_id(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except Exception:
        return False


async def _astream_graph(graph, input_state: dict, thread_id: str) -> AsyncIterator[dict]:
    """Yield token chunks + final citations from a LangGraph run。"""
    config = {"configurable": {"thread_id": thread_id}}
    # 我们跑完整图（generate 节点内部已经拼 prompt），这里从 retrieve 节点流式
    # streaming 通过 llm 的 astream_events 暴露给上层
    events: list[dict] = []
    async for ev in graph.astream_events(input_state, config=config, version="v1"):
        events.append(ev)
    return events


@router.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        raw = await ws.receive_text()
        payload = json.loads(raw)
        session_id = str(payload.get("session_id", ""))
        message = str(payload.get("message", ""))

        if not _validate_session_id(session_id):
            await ws.send_text(ErrorEvent(data="invalid session_id").model_dump_json())
            await ws.close()
            return

        if len(message) > 4000:
            await ws.send_text(ErrorEvent(data="message too long (>4000 chars)").model_dump_json())
            await ws.close()
            return

        if not message.strip():
            await ws.send_text(ErrorEvent(data="empty message").model_dump_json())
            await ws.close()
            return

        llm = get_llm(streaming=True)
        retriever = get_retriever(k=6)

        async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
            graph = build_graph(llm=llm, retriever=retriever, checkpointer=checkpointer)
            input_state = {"messages": [HumanMessage(content=message)]}
            config = {"configurable": {"thread_id": session_id}}

            full_answer = ""
            citations_payload: list[dict] = []
            finish_reason = "stop"

            try:
                # astream_events 让我们抓 generate / no_doc 节点的 token
                async for ev in graph.astream_events(input_state, config=config,
                                                    version="v1"):
                    kind = ev.get("event")
                    node = ev.get("metadata", {}).get("langgraph_node") or \
                           ev.get("name", "")
                    if kind == "on_chat_model_stream" and node in ("generate", "no_doc"):
                        chunk = ev.get("data", {}).get("chunk")
                        token = ""
                        if chunk is not None:
                            token = getattr(chunk, "content", "") or ""
                        if token:
                            full_answer += token
                            await ws.send_text(json.dumps(
                                {"event": "token", "data": token}, ensure_ascii=False))

                    if kind == "on_chain_end" and node in ("generate", "no_doc"):
                        out = (ev.get("data") or {}).get("output") or {}
                        cites = out.get("citations") if isinstance(out, dict) else None
                        if cites is not None:
                            citations_payload = cites
                        finish_reason = "no_doc" if node == "no_doc" else "stop"
            except Exception as exc:                              # noqa: BLE001
                await ws.send_text(ErrorEvent(data=f"agent error: {exc}").model_dump_json())
                await ws.close()
                return

        if citations_payload:
            await ws.send_text(json.dumps(
                {"event": "citation", "data": citations_payload}, ensure_ascii=False))
        await ws.send_text(json.dumps(
            {"event": "done", "data": {"finish_reason": finish_reason}}, ensure_ascii=False))
    except WebSocketDisconnect:
        return
    except Exception as exc:                                     # noqa: BLE001
        try:
            await ws.send_text(ErrorEvent(data=f"unexpected: {exc}").model_dump_json())
        except Exception:
            pass