# app/routes_ingest.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from .schemas import IngestRequest, IndexResult
from ingest.indexer import build_index


router = APIRouter()


@router.post("/api/ingest", response_model=IndexResult)
def ingest(req: IngestRequest) -> IndexResult:
    try:
        result = build_index(force=req.force)
    except Exception as exc:                              # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))
    return IndexResult(**result)