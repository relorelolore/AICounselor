# app/routes_health.py
from __future__ import annotations
from fastapi import APIRouter

from .schemas import HealthResponse
from rag.retriever import collection_count


router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    llm_ok = False
    try:
        from llm.client import get_llm
        get_llm(streaming=False).invoke("ping"[:1])      # 极简探测；超时容忍
        llm_ok = True
    except Exception:
        llm_ok = False
    return HealthResponse(
        status="ok" if llm_ok else "degraded",
        llm=llm_ok,
        chroma_count=collection_count(),
    )