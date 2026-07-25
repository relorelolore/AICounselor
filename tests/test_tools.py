"""Tests for the ``search_documents`` tool wrapper (agent/tools.py).

The ReAct agent invokes this tool when the LLM decides to consult the
document store. The tool returns ``(text, artifact)`` where ``text`` is the
human-readable snippet shown to the LLM and ``artifact`` is the structured
``Document`` list — downstream code reads the artifact to build citations.
"""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

from agent.prompts import format_docs_as_text
from agent.tools import build_search_documents_tool


class FakeRetriever:
    """Drop-in ``BaseRetriever`` stub for testing.

    Mirrors the shape used by the original test suite — takes a fixed list
    of ``Document`` objects and returns them unmodified for any query.
    """

    def __init__(self, docs): self.docs = list(docs)
    def invoke(self, q, **_): return list(self.docs)


# ---------------------------------------------------------------------------
# format_docs_as_text (used by the tool internally)
# ---------------------------------------------------------------------------

def test_format_docs_as_text_renders_index_source_page_content():
    docs = [
        Document(page_content="实践学分不少于 16 分",
                 metadata={"source": "/tmp/plan.pdf", "page": 3}),
    ]
    out = format_docs_as_text(docs)
    assert "[1] 来源：《plan.pdf》 第 3 页" in out
    assert "实践学分不少于 16 分" in out
    # i18n: 「来源：《》 第 N 页」 + 「内容：」 per spec §v2.4
    assert "内容：" in out


def test_format_docs_as_text_truncates_long_snippets():
    long = "X" * 500
    docs = [Document(page_content=long, metadata={"source": "a.pdf", "page": 1})]
    out = format_docs_as_text(docs)
    # snippet is truncated to 300 chars by default
    assert "X" * 300 in out
    assert "X" * 301 not in out


def test_format_docs_as_text_handles_empty_list():
    assert format_docs_as_text([]) == ""


def test_format_docs_as_text_collapses_newlines_in_content():
    docs = [Document(page_content="line1\nline2\nline3",
                     metadata={"source": "a.pdf", "page": 1})]
    out = format_docs_as_text(docs)
    # newlines normalized to single spaces so the LLM gets a clean block
    assert "line1 line2 line3" in out
    assert "\n" not in out.split("内容：")[1]


# ---------------------------------------------------------------------------
# build_search_documents_tool
# ---------------------------------------------------------------------------

def test_tool_invoke_returns_string_for_non_empty_results():
    tool = build_search_documents_tool(FakeRetriever([
        Document(page_content="实践学分不少于 16 分",
                 metadata={"source": "plan.pdf", "page": 3}),
    ]))
    # When called via ``tool.invoke({...})`` (not via ToolNode), only the
    # textual content is returned — the artifact is lifted into the
    # ToolMessage by ToolNode at agent-execution time.
    result = tool.invoke({"query": "实践学分"})
    assert isinstance(result, str)
    assert "实践学分不少于 16 分" in result
    assert "[1]" in result


def test_tool_invoke_returns_empty_marker_when_no_docs():
    tool = build_search_documents_tool(FakeRetriever([]))
    result = tool.invoke({"query": "没有的东西"})
    assert result == "（未检索到相关文档）"


def test_tool_docstring_warns_against_greeting_and_history():
    tool = build_search_documents_tool(FakeRetriever([]))
    desc = tool.description or ""
    # The docstring is the LLM's only cue about when NOT to call: it must
    # cover greetings and history questions (spec §v2.3).
    assert "寒暄" in desc or "问候" in desc
    assert "历史" in desc or "对话" in desc


def test_tool_artifact_is_document_list_via_toolnode():
    """When the agent invokes the tool, the resulting ``ToolMessage`` must
    carry the structured ``Document`` list in its ``artifact`` attribute so
    the chat route can build citations."""
    docs = [
        Document(page_content="实践学分不少于 16 分",
                 metadata={"source": "plan.pdf", "page": 3}),
    ]
    tool = build_search_documents_tool(FakeRetriever(docs))

    # Hand-roll a 2-step agent: first call the tool, then summarize.
    from langchain_core.language_models.fake_chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult

    class TwoShotCall(BaseChatModel):
        responses: list
        i: int = 0
        @property
        def _llm_type(self): return "two-shot"
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            r = self.responses[self.i]
            self.i += 1
            if isinstance(r, str):
                msg = AIMessage(content=r)
            else:
                msg = r
            return ChatResult(generations=[ChatGeneration(message=msg)])
        def bind_tools(self, tools, **kwargs): return self

    call_msg = AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "实践学分"}, "id": "1"},
    ])
    final_msg = AIMessage(content="根据 [1]，需要 16 分。")
    llm = TwoShotCall(responses=[call_msg, final_msg])
    g = create_react_agent(model=llm, tools=[tool], checkpointer=InMemorySaver())
    out = g.invoke({"messages": [HumanMessage(content="实践学分？")]},
                   config={"configurable": {"thread_id": "t"}})
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs, "expected a ToolMessage in the trace"
    assert tool_msgs[0].artifact == docs
    # The artifact should be raw Document objects, not strings.
    assert all(isinstance(d, Document) for d in tool_msgs[0].artifact)


def test_tool_artifact_is_empty_list_when_no_docs():
    """Empty retriever must surface ``artifact=[]`` and the standard
    textual sentinel so the LLM knows nothing was found."""
    from langchain_core.language_models.fake_chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult

    tool = build_search_documents_tool(FakeRetriever([]))

    class TwoShotCall(BaseChatModel):
        responses: list
        i: int = 0
        @property
        def _llm_type(self): return "two-shot"
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            r = self.responses[self.i]
            self.i += 1
            if isinstance(r, str):
                msg = AIMessage(content=r)
            else:
                msg = r
            return ChatResult(generations=[ChatGeneration(message=msg)])
        def bind_tools(self, tools, **kwargs): return self

    call_msg = AIMessage(content="", tool_calls=[
        {"name": "search_documents", "args": {"query": "x"}, "id": "1"},
    ])
    final_msg = AIMessage(content="查不到相关资料。")
    llm = TwoShotCall(responses=[call_msg, final_msg])
    g = create_react_agent(model=llm, tools=[tool], checkpointer=InMemorySaver())
    out = g.invoke({"messages": [HumanMessage(content="？")]},
                   config={"configurable": {"thread_id": "t"}})
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs[0].artifact == []
    assert tool_msgs[0].content == "（未检索到相关文档）"
