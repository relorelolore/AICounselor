from __future__ import annotations

from typing import Sequence, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Top-level state shape used by this app.

    Note: ``create_react_agent`` defines its own internal ``AgentState``
    (``messages`` with ``add_messages`` reducer + optional ``remaining_steps``).
    We keep this TypedDict around for documentation and so callers can reason
    about the shape, but the ReAct agent itself uses its own schema.

    The chat route (``app/routes_chat.py``) is responsible for populating the
    ``citations`` list after the graph returns: it walks ``messages`` for the
    ``search_documents`` ``ToolMessage`` and converts each tool's ``artifact``
    (a list of ``Document``) into ``[{filename, page, snippet}, ...]``.
    """

    messages: Sequence[BaseMessage]
    citations: list[dict]