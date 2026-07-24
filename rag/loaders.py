# rag/loaders.py
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document


def _load_pdf(path: str) -> list[Document]:
    from langchain_community.document_loaders import PyPDFLoader
    return PyPDFLoader(path).load()


def _load_pptx(path: str) -> list[Document]:
    from langchain_community.document_loaders import UnstructuredPowerPointLoader
    return UnstructuredPowerPointLoader(path).load()


def _load_docx(path: str) -> list[Document]:
    from langchain_community.document_loaders import UnstructuredWordDocumentLoader
    return UnstructuredWordDocumentLoader(path).load()


SUFFIX_LOADERS: dict[str, Callable[[str], list[Document]]] = {
    ".pdf": _load_pdf,
    ".pptx": _load_pptx,
    ".docx": _load_docx,
}


def load(path: str) -> list[Document]:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    ext = Path(path).suffix.lower()
    loader = SUFFIX_LOADERS.get(ext)
    if loader is None:
        print(f"[loaders] unsupported ext {ext} for {path}", file=sys.stderr)
        return []
    try:
        return loader(path)
    except Exception as exc:                   # noqa: BLE001
        print(f"[loaders] {path} failed: {exc}", file=sys.stderr)
        # 抛出由上层 indexer 捕获并记入 failed 列表
        raise
