# app/routes_chat.py
from __future__ import annotations
import json
import traceback
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .schemas import ErrorEvent
from agent.graph import build_graph
from llm.client import get_llm
from rag.citations import to_citations
from rag.retriever import get_retriever
from storage.paths import CHECKPOINT_DB


router = APIRouter()


def _validate_session_id(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except Exception:
        return False


def _extract_citations(messages) -> list[dict]:
    """Walk the final state messages and collect citations from every
    ``search_documents`` ToolMessage artifact. Deduplicates by
    ``(filename, page)`` keeping the first occurrence.
    """
    seen: set[tuple[str, int]] = set()
    out: list[dict] = []
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "search_documents":
            docs = m.artifact or []
            for cite in to_citations(docs):
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

                citations = _extract_citations(final_state["messages"])
                if citations:
                    await ws.send_text(json.dumps(
                        {"event": "citation", "data": citations}, ensure_ascii=False))

                # ReAct agent: if the model decided to call the search tool it
                # ends up as a ToolMessage (handled above for citations); if it
                # answered directly (greeting / meta / clarification) it never
                # produced a ToolMessage. Both cases are "stop" — the old
                # "no_doc" finish reason no longer applies.
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