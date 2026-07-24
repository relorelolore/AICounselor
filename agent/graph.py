from __future__ import annotations
from typing import Literal
from langgraph.graph import END, START, StateGraph

from .nodes import (
    make_generate_node,
    make_grade_node,
    make_no_doc_node,
    make_retrieve_node,
)
from .state import AgentState


def build_graph(*, llm, retriever, checkpointer):
    builder = StateGraph(AgentState)

    retrieve = make_retrieve_node(retriever)
    grade = make_grade_node(llm)
    generate = make_generate_node(llm)
    no_doc = make_no_doc_node(llm)

    builder.add_node("retrieve", retrieve)
    builder.add_node("grade", grade)
    builder.add_node("generate", generate)
    builder.add_node("no_doc", no_doc)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade")

    def _route(state: AgentState) -> Literal["generate", "no_doc"]:
        return "generate" if state.get("is_relevant") else "no_doc"

    builder.add_conditional_edges("grade", _route, {
        "generate": "generate",
        "no_doc": "no_doc",
    })
    builder.add_edge("generate", END)
    builder.add_edge("no_doc", END)

    return builder.compile(checkpointer=checkpointer)
