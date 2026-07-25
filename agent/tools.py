from __future__ import annotations

import os
from typing import Any

from langchain_core.documents import Document
from langchain_core.tools import tool

from .prompts import format_docs_as_text


def build_search_documents_tool(retriever: Any):
    """Factory: wrap a Chroma-like retriever as a LangChain tool.

    The returned tool is named ``search_documents``. LangChain's ``@tool`` decorator
    with ``response_format='content_and_artifact'`` causes the ``(content, artifact)``
    tuple return value to be lifted into a ``ToolMessage`` whose ``artifact`` field
    holds the original ``Document`` list — which downstream code (e.g. the chat
    route) can inspect to build the citations panel.
    """

    @tool(response_format="content_and_artifact")
    def search_documents(query: str) -> tuple[str, list[Document]]:
        """搜索学校培养方案、课程、毕业要求等文档资料；不要用于寒暄、问候、闲聊，或与本会话历史相关的问题。"""
        docs = retriever.invoke(query)
        if not docs:
            return "（未检索到相关文档）", []
        return format_docs_as_text(docs), list(docs)

    return search_documents


__all__ = ["build_search_documents_tool"]