# rag/splitter.py
from __future__ import annotations
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", "。", " ", ""]


def split(
    docs: list[Document],
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
    separators: list[str] | None = None,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators or DEFAULT_SEPARATORS,
        keep_separator=True,
        length_function=len,
    )
    return splitter.split_documents(docs)
