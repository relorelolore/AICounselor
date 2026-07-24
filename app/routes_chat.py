# app/routes_chat.py
from __future__ import annotations
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage
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

            try:
                final_state = await graph.ainvoke(input_state, config=config)

                # Emit the AI message content as a single token event.
                ai_messages = [
                    m for m in final_state["messages"] if isinstance(m, AIMessage)
                ]
                if ai_messages:
                    ai_content = ai_messages[-1].content or ""
                    if ai_content:
                        await ws.send_text(json.dumps(
                            {"event": "token", "data": ai_content}, ensure_ascii=False))

                citations = final_state.get("citations", []) or []
                if citations:
                    await ws.send_text(json.dumps(
                        {"event": "citation", "data": citations}, ensure_ascii=False))

                finish_reason = "no_doc" if not final_state.get("is_relevant") else "stop"
                await ws.send_text(json.dumps(
                    {"event": "done", "data": {"finish_reason": finish_reason}},
                    ensure_ascii=False))
            except WebSocketDisconnect:
                return
            except Exception as exc:                              # noqa: BLE001
                await ws.send_text(ErrorEvent(data=f"agent error: {exc}").model_dump_json())
                await ws.close()
                return

    except WebSocketDisconnect:
        return
    except Exception as exc:                                     # noqa: BLE001
        try:
            await ws.send_text(ErrorEvent(data=f"unexpected: {exc}").model_dump_json())
        except Exception:
            pass