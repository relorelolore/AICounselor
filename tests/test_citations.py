import os
import tempfile

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent.graph import build_graph
from rag.citations import to_citations


class _ScriptedChat(BaseChatModel):
    """First call → tool_call; subsequent calls → final AIMessage."""
    responses: list
    i: int = 0

    @property
    def _llm_type(self) -> str:
        return "test-scripted-chat"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        r = self.responses[self.i]
        self.i += 1
        msg = AIMessage(content=r) if isinstance(r, str) else r
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self


class _StaticRetriever:
    def __init__(self, docs):
        self.docs = docs

    def invoke(self, query):
        return self.docs


def test_citations_basic():
    docs = [
        Document(
            page_content="培养方案要求实践学分不少于 16 分。" * 10,
            metadata={"source": "plan.pdf", "page": 3},
        ),
        Document(
            page_content="通识选修课包括人文与社会两大模块。" * 5,
            metadata={"source": "plan.pdf", "page": 5},
        ),
    ]
    out = to_citations(docs, snippet_len=80)
    assert len(out) == 2
    assert out[0]["index"] == 1
    assert out[0]["filename"] == "plan.pdf"
    assert out[0]["page"] == 3
    assert len(out[0]["snippet"]) <= 80
    assert out[1]["index"] == 2


def test_citations_filename_from_path():
    docs = [
        Document(
            page_content="x",
            metadata={"source": "/abs/path/培养方案.pdf", "page": 1},
        )
    ]
    out = to_citations(docs)
    assert out[0]["filename"] == "培养方案.pdf"


def test_citations_missing_page_defaults_to_zero():
    docs = [Document(page_content="x", metadata={"source": "a.pdf"})]
    out = to_citations(docs)
    assert out[0]["page"] == 0


def test_citations_empty():
    assert to_citations([]) == []


# ---------------------------------------------------------------------------
# Regression: after the SQLite checkpointer round-trips a ToolMessage, the
# `artifact` field comes back as `list[dict]` (Document serialized as
# `{id, metadata, page_content, type: 'Document'}`). `to_citations` must
# handle that without raising ``AttributeError: 'dict' object has no
# attribute 'metadata'`` — the user-reported bug.
# ---------------------------------------------------------------------------

def test_citations_accepts_dict_artifact_shaped_like_document():
    """Plain dict shape that JsonPlusSerializer produces — mirror the bad input."""
    docs = [
        {
            "id": None,
            "metadata": {"source": "plan.pdf", "page": 3},
            "page_content": "实践学分不少于 16 分",
            "type": "Document",
        },
    ]
    out = to_citations(docs)
    assert len(out) == 1
    assert out[0] == {
        "index": 1,
        "filename": "plan.pdf",
        "page": 3,
        "snippet": "实践学分不少于 16 分",
    }


@pytest.mark.asyncio
async def test_citations_after_checkpointer_round_trip():
    """End-to-end: turn 1 saves state; turn 2 reloads it, then ``to_citations``
    on the persisted artifact must not raise ``AttributeError``.

    Without the fix this test reproduces the production error: the checkpointer
    persists ToolMessage.artifact as JSON; Document pydantic objects re-emerge
    as plain dicts on reload, and ``document.metadata`` blows up.
    """
    docs = [Document(page_content="实践学分不少于 16 分",
                     metadata={"source": "plan.pdf", "page": 3})]
    call_msg = AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "实践"}, "id": "call_1"},
    ])
    final = AIMessage(content="根据 [1]，需要 16 分。")

    with tempfile.TemporaryDirectory() as tmp:
        ckpt = os.path.join(tmp, "ckpt.db")
        async with AsyncSqliteSaver.from_conn_string(ckpt) as cp1:
            g1 = build_graph(
                llm=_ScriptedChat(responses=[call_msg, final]),
                retriever=_StaticRetriever(docs),
                checkpointer=cp1,
            )
            await g1.ainvoke(
                {"messages": [HumanMessage(content="实践学分？")]},
                config={"configurable": {"thread_id": "t1"}},
            )

        # Re-open the checkpointer — simulates the second WS turn.
        async with AsyncSqliteSaver.from_conn_string(ckpt) as cp2:
            g2 = build_graph(
                llm=_ScriptedChat(responses=[final]),
                retriever=_StaticRetriever(docs),
                checkpointer=cp2,
            )
            out = await g2.ainvoke(
                {"messages": [HumanMessage(content="再说一次")]},
                config={"configurable": {"thread_id": "t1"}},
            )
            tool_ms = [
                m for m in out["messages"]
                if isinstance(m, ToolMessage) and m.name == "search_documents"
            ]
            assert tool_ms, "expected at least one search_documents ToolMessage"
            for tm in tool_ms:
                # The line that raised in production.
                cites = to_citations(tm.artifact or [])
                assert cites, "to_citations must produce a non-empty list"
                for c in cites:
                    assert "filename" in c and "page" in c and "snippet" in c


@pytest.mark.asyncio
async def test_citations_do_not_leak_across_turns():
    """Regression: 第二轮（不调工具）的 citations 不能包含第一轮的引用。

    `routes_chat.py` 走 `_extract_citations(final_state["messages"])`，而
    `final_state["messages"]` 包含整个 thread 的持久化历史 —— 如果不过滤，
    第一轮的 ToolMessage citations 会被原样带回，导致前端「参考资料」面板
    累积。修复：用 `aget_state` 拿到旧消息 ID，只取本轮新增消息作为来源。
    """
    docs_t1 = [Document(page_content="第一轮：培养方案要求 16 学分。",
                        metadata={"source": "plan.pdf", "page": 3})]
    call_t1 = AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "学分"}, "id": "call_1"},
    ])
    answer_t1 = AIMessage(content="根据 [1]，需要 16 学分。")

    # 第二轮：LLM 不调工具，直接回答。
    answer_t2 = AIMessage(content="好的，记下来了。")

    def _ids(messages):
        return {m.id for m in messages if getattr(m, "id", None)}

    def _cites_from(messages, prior_ids):
        """Mirror `routes_chat.py` post-fix logic."""
        from app.routes_chat import _extract_citations
        new = [m for m in messages
               if getattr(m, "id", None) and m.id not in prior_ids]
        return _extract_citations(new)

    with tempfile.TemporaryDirectory() as tmp:
        ckpt = os.path.join(tmp, "ckpt.db")
        # --- turn 1 ---
        async with AsyncSqliteSaver.from_conn_string(ckpt) as cp1:
            g1 = build_graph(
                llm=_ScriptedChat(responses=[call_t1, answer_t1]),
                retriever=_StaticRetriever(docs_t1),
                checkpointer=cp1,
            )
            out1 = await g1.ainvoke(
                {"messages": [HumanMessage(content="学分要求？")]},
                config={"configurable": {"thread_id": "t-across"}},
            )
            turn1_cites = _cites_from(out1["messages"], prior_ids=set())
            assert len(turn1_cites) == 1
            assert turn1_cites[0]["filename"] == "plan.pdf"
            prior_after_t1 = _ids(out1["messages"])

        # --- turn 2 (no tool call) ---
        async with AsyncSqliteSaver.from_conn_string(ckpt) as cp2:
            g2 = build_graph(
                llm=_ScriptedChat(responses=[answer_t2]),
                retriever=_StaticRetriever(docs_t1),
                checkpointer=cp2,
            )
            # Simulate the snapshot taken in routes_chat.py BEFORE ainvoke.
            snapshot = await g2.aget_state(
                {"configurable": {"thread_id": "t-across"}}
            )
            prior_ids = _ids((snapshot.values or {}).get("messages", []) or [])

            out2 = await g2.ainvoke(
                {"messages": [HumanMessage(content="好的")]},
                config={"configurable": {"thread_id": "t-across"}},
            )
            turn2_cites = _cites_from(out2["messages"], prior_ids=prior_ids)

            # 第二轮没调工具，所以本轮 citations 应为空 —— 不应带回第一轮的。
            assert turn2_cites == [], (
                f"第二轮不应累积第一轮的 citations，但拿到了 {turn2_cites}。"
                "很可能是 routes_chat.py 的 prior_message_ids 过滤失效。"
            )
