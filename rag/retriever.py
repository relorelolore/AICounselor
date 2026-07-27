# rag/retriever.py
from __future__ import annotations

import os
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.vectorstores import VectorStoreRetriever

from llm.config import get_rag_settings

from .embeddings import get_embeddings

# Patch chromadb 0.6.x's posthog telemetry call to match posthog >= 7.x's
# signature. Without this, every Chroma() init logs
# `capture() takes 1 positional argument but 3 were given` (and the same
# again on first collection). The patch is idempotent — it's also applied
# at app/main.py startup for the uvicorn path; the guard makes repeated
# applications harmless. Applied here so the `python -m ingest` path
# (which does not import app/main.py) is also covered.
import posthog  # noqa: E402
import chromadb.telemetry.product.posthog as _chroma_posthog  # noqa: E402

if not getattr(_chroma_posthog.Posthog, "_AICounselor_patched", False):
    _orig_direct_capture = _chroma_posthog.Posthog._direct_capture
    _POSTHOG_EVENT_SETTINGS = _chroma_posthog.POSTHOG_EVENT_SETTINGS

    def _patched_direct_capture(self, event):  # type: ignore[no-redef]
        try:
            posthog.capture(
                event.name,
                distinct_id=self.user_id,
                properties={
                    **event.properties,
                    **_POSTHOG_EVENT_SETTINGS,
                    **self.context,
                },
            )
        except Exception as exc:
            _chroma_posthog.logger.error(
                f"Failed to send telemetry event {event.name}: {exc}"
            )

    _chroma_posthog.Posthog._direct_capture = _patched_direct_capture
    _chroma_posthog.Posthog._AICounselor_patched = True


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