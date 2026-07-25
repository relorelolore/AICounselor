from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from .prompts import COUNSELOR_SYSTEM_PROMPT
from .tools import build_search_documents_tool


def build_graph(*, llm, retriever, checkpointer):
    """Create a ReAct agent that uses ``search_documents`` as its only tool.

    The agent is a ``langgraph.prebuilt.create_react_agent`` instance. The LLM
    decides each turn whether to call the search tool or reply directly (handy
    for greetings, meta-questions, and follow-ups about the conversation
    history).

    Returns a compiled graph. Callers invoke it via::

        graph.ainvoke({"messages": [HumanMessage(...)]},
                      config={"configurable": {"thread_id": ...}})

    Note on the prompt argument: in langgraph 0.6.x this parameter is named
    ``prompt`` (it was ``state_modifier`` in 0.2.x). The callable receives the
    current state dict and must return the message list to send to the model —
    we prepend a fresh ``SystemMessage`` each turn so the LLM always sees the
    counselor persona instructions.
    """
    search_tool = build_search_documents_tool(retriever)
    agent = create_react_agent(
        model=llm,
        tools=[search_tool],
        prompt=lambda state: [SystemMessage(content=COUNSELOR_SYSTEM_PROMPT)]
        + list(state["messages"]),
        checkpointer=checkpointer,
    )
    return agent