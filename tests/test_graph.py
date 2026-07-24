from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from agent.graph import build_graph
from tests.test_nodes import FakeRetriever, FakeChat


def _graph(llm_content: str, docs):
    return build_graph(
        llm=FakeChat(llm_content),
        retriever=FakeRetriever(docs),
        checkpointer=InMemorySaver(),
    )


def test_routes_through_generate_when_relevant():
    docs = [Document(page_content="实践学分不少于 16 分",
                      metadata={"source":"plan.pdf","page":3})]
    # 第一次用于 grade（relevant=true），第二次用于 generate 内容
    class TwoShot:
        def __init__(self): self.n = 0
        def invoke(self, msgs, **_):
            self.n += 1
            if self.n == 1:
                return AIMessage(content='{"relevant": true}')
            return AIMessage(content="根据 [1]，需要 16 分。")
    g = build_graph(llm=TwoShot(), retriever=FakeRetriever(docs),
                    checkpointer=InMemorySaver())
    out = g.invoke(
        {"messages": [HumanMessage(content="实践学分要求？")]},
        config={"configurable": {"thread_id": "t1"}},
    )
    msgs = out["messages"]
    assert any(isinstance(m, AIMessage) and "16 分" in m.content for m in msgs)
    assert out["citations"] and out["citations"][0]["filename"] == "plan.pdf"


def test_routes_through_no_doc_when_irrelevant():
    class TwoShot:
        def __init__(self): self.n = 0
        def invoke(self, msgs, **_):
            self.n += 1
            if self.n == 1:
                return AIMessage(content='{"relevant": false}')
            return AIMessage(content="未在培养方案中查到相关说法，建议咨询学院教务。")
    docs = [Document(page_content="无关内容", metadata={"source":"a.pdf","page":1})]
    g = build_graph(llm=TwoShot(), retriever=FakeRetriever(docs),
                    checkpointer=InMemorySaver())
    out = g.invoke(
        {"messages": [HumanMessage(content="无关问题")]},
        config={"configurable": {"thread_id": "t2"}},
    )
    assert any(isinstance(m, AIMessage) and "未在培养方案中查到" in m.content for m in out["messages"])
    assert out["citations"] == []


def test_routes_through_no_doc_when_no_retrieved():
    class OneShot:
        n = 0
        def invoke(self, msgs, **_):
            self.n += 1
            return AIMessage(content="未在培养方案中查到相关说法，建议咨询学院教务。")
    g = build_graph(llm=OneShot(), retriever=FakeRetriever([]),
                    checkpointer=InMemorySaver())
    out = g.invoke(
        {"messages": [HumanMessage(content="无文档时")]},
        config={"configurable": {"thread_id": "t3"}},
    )
    assert any(isinstance(m, AIMessage) and "未在培养方案中查到" in m.content for m in out["messages"])
