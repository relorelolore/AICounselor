from __future__ import annotations
import operator
from typing import Annotated, TypedDict
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    retrieved_docs: list[Document]
    is_relevant: bool
    citations: list[dict]
