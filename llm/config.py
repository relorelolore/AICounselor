# llm/config.py
"""LLM / RAG / Embedding runtime config.

Module-level singletons (`_llm_cfg`, `_rag_cfg`, `_emb_cfg`) are mutated
in place by `update_*_settings()` so subsequent reads (e.g. `get_llm()`)
see the new values. Defaults come from env vars at import time; admin
backend can override at runtime via the settings routes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields


@dataclass
class LLMConfig:
    base_url: str
    model_name: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout: int
    top_p: float
    frequency_penalty: float
    presence_penalty: float


@dataclass
class RAGConfig:
    k: int
    chunk_size: int
    chunk_overlap: int


@dataclass
class EmbeddingConfig:
    model: str


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _build_llm_defaults() -> LLMConfig:
    return LLMConfig(
        base_url=_env("LLAMACPP_BASE_URL", "http://localhost:8848/v1"),
        model_name=_env("MODEL_NAME", "g0chu-Qwen3.6-35B-A3B-NVFP4"),
        api_key=_env("LLAMACPP_API_KEY", "llama.cpp"),
        temperature=float(_env("TEMPERATURE", "0.3")),
        max_tokens=int(_env("MAX_TOKENS", "2048")),
        timeout=int(_env("LLM_TIMEOUT", "120")),
        top_p=float(_env("TOP_P", "1.0")),
        frequency_penalty=float(_env("FREQUENCY_PENALTY", "0.0")),
        presence_penalty=float(_env("PRESENCE_PENALTY", "0.0")),
    )


def _build_rag_defaults() -> RAGConfig:
    return RAGConfig(
        k=int(_env("RETRIEVE_K", "6")),
        chunk_size=int(_env("CHUNK_SIZE", "500")),
        chunk_overlap=int(_env("CHUNK_OVERLAP", "80")),
    )


def _build_emb_defaults() -> EmbeddingConfig:
    return EmbeddingConfig(model=_env("EMBED_MODEL", "BAAI/bge-m3"))


_llm_cfg: LLMConfig = _build_llm_defaults()
_rag_cfg: RAGConfig = _build_rag_defaults()
_emb_cfg: EmbeddingConfig = _build_emb_defaults()


def get_llm_settings() -> LLMConfig:
    return _llm_cfg


def get_rag_settings() -> RAGConfig:
    return _rag_cfg


def get_embedding_settings() -> EmbeddingConfig:
    return _emb_cfg


def _apply_patch(cfg_obj, patch: dict) -> None:
    """Apply patch in place; raise ValueError on unknown fields."""
    valid = {f.name for f in fields(type(cfg_obj))}
    for k in patch:
        if k not in valid:
            raise ValueError(f"unknown setting field: {k!r}")
    for k, v in patch.items():
        setattr(cfg_obj, k, v)


def update_llm_settings(patch: dict) -> None:
    _apply_patch(_llm_cfg, patch)


def update_rag_settings(patch: dict) -> None:
    _apply_patch(_rag_cfg, patch)


def update_embedding_settings(patch: dict) -> None:
    _apply_patch(_emb_cfg, patch)


def reset_settings_for_tests() -> None:
    """Rebuild singletons from current env. Tests only."""
    global _llm_cfg, _rag_cfg, _emb_cfg
    _llm_cfg = _build_llm_defaults()
    _rag_cfg = _build_rag_defaults()
    _emb_cfg = _build_emb_defaults()


# ---- Backwards-compat module-level aliases (read from singleton at import) ----
# Some legacy code (e.g. app/routes_health.py) reads these at module load.
# They are captured at import time and are NOT hot-reloadable — restart-required
# fields per REQUIRES_RESTART["llm"] (base_url, model_name).
LLAMACPP_BASE_URL: str = _llm_cfg.base_url
MODEL_NAME: str = _llm_cfg.model_name