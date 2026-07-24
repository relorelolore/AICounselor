from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from agent.nodes import make_retrieve_node, make_grade_node, make_generate_node, make_no_doc_node
from agent.state import AgentState


class FakeRetriever:
    def __init__(self, docs): self.docs = docs
    def invoke(self, q, **_): return list(self.docs)


class FakeChat:
    def __init__(self, content: str): self.content = content
    def invoke(self, msgs, **_): return AIMessage(content=self.content)


def test_retrieve_node_populates_state():
    r = FakeRetriever([
        Document(page_content="实践学分不少于 16 分", metadata={"source": "plan.pdf", "page": 3}),
    ])
    state: AgentState = {"messages": [HumanMessage(content="实践学分？")],
                         "retrieved_docs": [], "is_relevant": False, "citations": []}
    out = make_retrieve_node(r)(state)
    assert len(out["retrieved_docs"]) == 1
    assert out["retrieved_docs"][0].page_content.startswith("实践学分")


def test_grade_node_parses_json_yes():
    llm = FakeChat('{"relevant": true, "reason": "ok"}')
    state: AgentState = {"messages": [HumanMessage(content="问题")],
                         "retrieved_docs": [Document(page_content="答案", metadata={"source":"a.pdf"})],
                         "is_relevant": False, "citations": []}
    out = make_grade_node(llm)(state)
    assert out["is_relevant"] is True


def test_grade_node_parses_json_no():
    llm = FakeChat('{"relevant": false, "reason": "无关"}')
    state: AgentState = {"messages": [HumanMessage(content="问题")],
                         "retrieved_docs": [Document(page_content="x", metadata={"source":"a.pdf"})],
                         "is_relevant": True, "citations": []}
    out = make_grade_node(llm)(state)
    assert out["is_relevant"] is False


def test_grade_node_invalid_json_defaults_false():
    llm = FakeChat("不是 JSON")
    state: AgentState = {"messages": [HumanMessage(content="q")],
                         "retrieved_docs": [Document(page_content="x", metadata={"source":"a.pdf"})],
                         "is_relevant": True, "citations": []}
    out = make_grade_node(llm)(state)
    assert out["is_relevant"] is False


def test_generate_node_appends_assistant_message_and_citations():
    llm = FakeChat("根据文档 [1]，需要 16 分。")
    docs = [Document(page_content="实践学分不少于 16 分", metadata={"source":"plan.pdf","page":3})]
    state: AgentState = {"messages": [HumanMessage(content="问题")],
                         "retrieved_docs": docs, "is_relevant": True, "citations": []}
    out = make_generate_node(llm)(state)
    assert out["messages"][-1].content.startswith("根据文档 [1]")
    assert out["citations"] and out["citations"][0]["filename"] == "plan.pdf"


def test_no_doc_node_appends_advisor_message():
    llm = FakeChat("未在培养方案中查到相关说法，建议咨询学院教务。")
    state: AgentState = {"messages": [HumanMessage(content="问题")],
                         "retrieved_docs": [], "is_relevant": False, "citations": []}
    out = make_no_doc_node(llm)(state)
    assert "未在培养方案中查到" in out["messages"][-1].content
    assert out["citations"] == []
