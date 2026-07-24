from __future__ import annotations
import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.vectorstores import VectorStoreRetriever

from .prompts import (
    GENERATE_PROMPT,
    GRADE_PROMPT,
    SYSTEM_PROMPT,
    format_docs_compact,
    format_docs_full,
)
from .state import AgentState
from rag.citations import to_citations


def _last_user_message(state: AgentState) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            return m.content
    return ""


def _history_text(state: AgentState, *, max_chars: int = 2000) -> str:
    parts = []
    for m in state["messages"][-8:]:                       # 截断
        role = "学生" if isinstance(m, HumanMessage) else "辅导员"
        parts.append(f"{role}：{m.content}")
    return "\n".join(parts)[-max_chars:]


def make_retrieve_node(retriever: VectorStoreRetriever):
    """返回 retrieve 节点函数。闭包绑定 retriever 以便测试注入 fake。"""
    def _node(state: AgentState) -> dict:
        query = _last_user_message(state)
        docs = retriever.invoke(query) if query else []
        return {"retrieved_docs": list(docs)}
    return _node


def make_grade_node(llm):
    def _node(state: AgentState) -> dict:
        query = _last_user_message(state)
        docs = state["retrieved_docs"]
        if not docs:
            return {"is_relevant": False}
        formatted = format_docs_compact(docs)
        prompt = GRADE_PROMPT.format(docs=formatted, question=query)
        resp = llm.invoke(prompt)
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        # 解析 JSON
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if not m:
            return {"is_relevant": False}
        try:
            data = json.loads(m.group(0))
            return {"is_relevant": data.get("relevant") is True}
        except Exception:
            return {"is_relevant": False}
    return _node


def make_generate_node(llm):
    def _node(state: AgentState) -> dict:
        docs = state["retrieved_docs"]
        snippets = [d.page_content[:300] for d in docs]
        formatted = format_docs_full(docs, snippets)
        history = _history_text(state)
        prompt = GENERATE_PROMPT.format(docs=formatted, history=history,
                                        question=_last_user_message(state))
        # 把 system prompt 与 user 拼接，简单模型够用
        resp = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        text = resp.content if hasattr(resp, "content") else str(resp)
        citations = to_citations(docs)
        return {
            "messages": [AIMessage(content=text)],
            "citations": citations,
        }
    return _node


def make_no_doc_node(llm):
    def _node(state: AgentState) -> dict:
        prompt = (
            "学生问题：" + _last_user_message(state) +
            "\n历史对话：\n" + _history_text(state) +
            "\n请礼貌告知未在培养方案中找到相关说法，并建议联系学院教务。"
        )
        resp = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        text = resp.content if hasattr(resp, "content") else str(resp)
        return {"messages": [AIMessage(content=text)], "citations": []}
    return _node
