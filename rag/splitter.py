# rag/splitter.py
"""Chinese-aware splitter that reads chunk_size/chunk_overlap from runtime config.

Defaults come from `get_rag_settings()`; explicit `chunk_size`/`chunk_overlap`
kwargs override for backward compatibility with existing tests/callers.
"""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from llm.config import get_rag_settings


DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", "。", " ", ""]


def split(
    docs: list[Document],
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    separators: list[str] | None = None,
) -> list[Document]:
    rag = get_rag_settings()
    eff_chunk_size = chunk_size if chunk_size is not None else rag.chunk_size
    eff_chunk_overlap = chunk_overlap if chunk_overlap is not None else rag.chunk_overlap
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=eff_chunk_size,
        chunk_overlap=eff_chunk_overlap,
        separators=separators or DEFAULT_SEPARATORS,
        keep_separator=True,
        length_function=len,
    )
    return splitter.split_documents(docs)