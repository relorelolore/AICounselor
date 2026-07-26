# app/admin/schemas.py
"""Pydantic models for the /api/admin/* HTTP routes."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str
    created_at: float
    last_login_at: float | None = None


class MeResponse(BaseModel):
    username: str
    created_at: float
    last_login_at: float | None = None


class AccountPublic(BaseModel):
    id: str
    username: str
    created_at: float
    updated_at: float
    last_login_at: float | None = None
    failed_attempts: int
    locked: bool


class AccountCreate(BaseModel):
    # NOTE: no Field(min_length=...) — validation lives in app.admin.accounts
    # so the route returns 400 (via WeakPasswordError/InvalidUsernameError)
    # instead of FastAPI's 422 from Pydantic.
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_password: str | None = None
    new_password: str | None = Field(default=None, min_length=6)
    unlock: bool | None = None


class LLMSettings(BaseModel):
    base_url: str
    model_name: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout: int
    top_p: float
    frequency_penalty: float
    presence_penalty: float


class RetrievalSettings(BaseModel):
    k: int
    chunk_size: int
    chunk_overlap: int


class PathsSettings(BaseModel):
    documents_dir: str
    data_dir: str
    chroma_collection: str


class EmbeddingSettings(BaseModel):
    model: str


class SettingsPatch(BaseModel):
    sections: dict[str, dict[str, Any]]


class ReindexRequest(BaseModel):
    force: bool = False
