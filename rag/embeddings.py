from __future__ import annotations

import os
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings


DEFAULT_EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    # NOTE: langchain-huggingface 0.3.x's HuggingFaceEmbeddings.__init__ eagerly
    # creates a SentenceTransformer, so this cache cannot defer model loading
    # beyond first call. A future task could introduce a thin lazy wrapper if
    # startup cost becomes a concern.
    return HuggingFaceEmbeddings(
        model_name=DEFAULT_EMBED_MODEL,
        model_kwargs={"device": _detect_device()},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 8},
    )


def _detect_device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"
