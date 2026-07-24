# app/schemas.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str                # "ok" | "degraded"
    llm: bool
    chroma_count: int


class IngestRequest(BaseModel):
    force: bool = False


class IndexResult(BaseModel):
    added: int
    skipped: int
    failed: list[dict] = Field(default_factory=list)
    meta_written: bool = True


class ChatMessage(BaseModel):
    session_id: str
    message: str


class TokenEvent(BaseModel):
    event: str = "token"
    data: str


class CitationEvent(BaseModel):
    event: str = "citation"
    data: list[dict]


class DoneEvent(BaseModel):
    event: str = "done"
    data: dict


class ErrorEvent(BaseModel):
    event: str = "error"
    data: str