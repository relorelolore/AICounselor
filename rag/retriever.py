# rag/retriever.py
from __future__ import annotations

import os
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.vectorstores import VectorStoreRetriever

from llm.config import get_rag_settings

from .embeddings import get_embeddings


COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION", "counselor")


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "./data")


def _persist_dir() -> str:
    return os.path.join(_data_dir(), "chroma")


@lru_cache(maxsize=1)
def get_chroma() -> Chroma:
    os.makedirs(_persist_dir(), exist_ok=True)
    return Chroma(
        persist_directory=_persist_dir(),
        embedding_function=get_embeddings(),
        collection_name=COLLECTION_NAME,
    )


def get_retriever(*, k: int | None = None) -> VectorStoreRetriever:
    effective_k = k if k is not None else get_rag_settings().k
    return get_chroma().as_retriever(
        search_type="similarity",
        search_kwargs={"k": effective_k},
    )


def collection_count() -> int:
    try:
        return get_chroma()._collection.count()
    except Exception:
        return 0