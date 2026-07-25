"""Integration tests for the ReAct agent (agent/graph.py).

The agent delegates the "should I call the tool?" decision to the LLM, so
each scenario drives a hand-rolled ``RotatingFakeChat`` that yields a
scripted sequence of ``AIMessage`` (with or without ``tool_calls``) so the
graph terminates without hitting llama.cpp.

Scenario mapping (spec §v2.5):
  - Greeting: model decides not to call tool -> no ToolMessage.
  - Document question: model calls tool -> has ToolMessage with artifact.
  - Memory question: model decides not to call tool -> no ToolMessage.
"""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from agent.graph import build_graph
from tests.test_tools import FakeRetriever


class RotatingFakeChat(BaseChatModel):
    """Drop-in chat model that returns the next scripted response each call.

    Each entry in ``responses`` may be either a ``str`` (returned as
    ``AIMessage(content=...)``) or an ``AIMessage`` instance (used as-is,
    which is how we inject ``tool_calls`` for the ReAct loop).

    ``bind_tools`` returns ``self`` because the ReAct agent expects an
    LLM bound to its tool surface; our fake is already aware of the tools
    from the test's perspective, so we don't need to mutate state.
    """

    responses: list
    i: int = 0

    @property
    def _llm_type(self) -> str:
        return "rotating-fake-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        r = self.responses[self.i]
        self.i += 1
        msg = AIMessage(content=r) if isinstance(r, str) else r
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self


# ---------------------------------------------------------------------------
# Greeting — model replies directly without invoking the tool.
# ---------------------------------------------------------------------------

def test_greeting_no_tool_call_no_tool_message():
    """Greeting flow: AIMessage with no tool_calls -> ToolMessage absent."""
    llm = RotatingFakeChat(responses=["嗨！有什么可以帮你的？"])
    g = build_graph(
        llm=llm,
        retriever=FakeRetriever([]),
        checkpointer=InMemorySaver(),
    )
    out = g.invoke(
        {"messages": [HumanMessage(content="你好")]},
        config={"configurable": {"thread_id": "greeting"}},
    )
    msgs = out["messages"]
    # Only the human turn and one final AI turn — no tool use.
    assert len(msgs) == 2
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)
    assert msgs[1].content == "嗨！有什么可以帮你的？"
    assert not getattr(msgs[1], "tool_calls", None), "no tool_calls for greeting"
    assert not any(isinstance(m, ToolMessage) for m in msgs), "no ToolMessage"


# ---------------------------------------------------------------------------
# Document question — model calls the tool, gets a ToolMessage, then answers.
# ---------------------------------------------------------------------------

def test_document_question_calls_tool_and_artifact_holds_docs():
    """RAG flow: AIMessage with tool_calls -> ToolMessage with artifact -> final answer."""
    docs = [
        Document(page_content="实践学分不少于 16 分",
                 metadata={"source": "plan.pdf", "page": 3}),
    ]
    call_msg = AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "实践学分"}, "id": "call_1"},
    ])
    final_msg = AIMessage(content="根据 [1]，需要 16 分。")
    llm = RotatingFakeChat(responses=[call_msg, final_msg])
    g = build_graph(
        llm=llm,
        retriever=FakeRetriever(docs),
        checkpointer=InMemorySaver(),
    )
    out = g.invoke(
        {"messages": [HumanMessage(content="实践学分要求？")]},
        config={"configurable": {"thread_id": "doc_q"}},
    )
    msgs = out["messages"]
    assert isinstance(msgs[0], HumanMessage)
    # Step 1: AIMessage carrying the tool_calls payload.
    assert isinstance(msgs[1], AIMessage)
    assert msgs[1].tool_calls and msgs[1].tool_calls[0]["name"] == "search_documents"
    # Step 2: ToolMessage with the Document artifact preserved.
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].artifact == docs
    assert all(isinstance(d, Document) for d in tool_msgs[0].artifact)
    # Step 3: final AIMessage with the summary.
    assert msgs[-1].content == "根据 [1]，需要 16 分。"
    assert not getattr(msgs[-1], "tool_calls", None) or msgs[-1].tool_calls == []


# ---------------------------------------------------------------------------
# Memory question — model answers from history without invoking the tool.
# ---------------------------------------------------------------------------

def test_memory_question_no_tool_call():
    """Memory flow: model decides not to call tool -> final answer from history."""
    prior = AIMessage(content="你刚才说的是：实践学分不少于 16 分。")
    llm = RotatingFakeChat(responses=[prior])
    g = build_graph(
        llm=llm,
        retriever=FakeRetriever([]),
        checkpointer=InMemorySaver(),
    )
    out = g.invoke(
        {"messages": [HumanMessage(content="我刚才问了什么？")]},
        config={"configurable": {"thread_id": "memory"}},
    )
    msgs = out["messages"]
    assert len(msgs) == 2
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)
    assert "刚" in msgs[1].content
    assert not getattr(msgs[1], "tool_calls", None)
    assert not any(isinstance(m, ToolMessage) for m in msgs), "no ToolMessage for memory"
