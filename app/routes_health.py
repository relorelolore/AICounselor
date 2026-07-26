# app/routes_health.py
from __future__ import annotations

import time
from threading import Lock
from urllib.request import Request, urlopen

from fastapi import APIRouter

from llm.config import LLAMACPP_BASE_URL, get_llm_settings
from rag.retriever import collection_count

from .schemas import HealthResponse


router = APIRouter()

_PROBE_TTL_SECONDS = 10.0
_probe_cache: tuple[float, bool] | None = None
_probe_lock = Lock()


def _probe_llm() -> bool:
    """Quick HTTP probe of the llama.cpp /v1/models endpoint.

    Sends Authorization: Bearer <api_key> so authenticated OpenAI-compatible
    proxies (OpenAI / Azure / etc.) also probe green; llama.cpp ignores the
    header.
    """
    api_key = get_llm_settings().api_key
    req = Request(
        f"{LLAMACPP_BASE_URL.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urlopen(req, timeout=2.0) as response:
            return response.status == 200
    except Exception:
        return False


def _llm_status_cached() -> bool:
    global _probe_cache
    with _probe_lock:
        if _probe_cache is not None:
            timestamp, ok = _probe_cache
            if time.monotonic() - timestamp < _PROBE_TTL_SECONDS:
                return ok
        ok = _probe_llm()
        _probe_cache = (time.monotonic(), ok)
        return ok


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    llm_ok = _llm_status_cached()
    return HealthResponse(
        status="ok" if llm_ok else "degraded",
        llm=llm_ok,
        chroma_count=collection_count(),
    )