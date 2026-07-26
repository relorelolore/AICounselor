# app/admin/settings.py
"""Persisted admin settings + validation + restart-required tagging."""
from __future__ import annotations

from storage.admin_db import settings as db_settings


SECTIONS: tuple[str, ...] = ("llm", "retrieval", "paths", "embedding")


DEFAULTS: dict[str, dict] = {
    "llm": {
        "base_url": "http://localhost:8848/v1",
        "model_name": "g0chu-Qwen3.6-35B-A3B-NVFP4",
        "api_key": "llama.cpp",
        "temperature": 0.3,
        "max_tokens": 2048,
        "timeout": 120,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    "retrieval": {
        "k": 6,
        "chunk_size": 500,
        "chunk_overlap": 80,
    },
    "paths": {
        "documents_dir": "./Documents",
        "data_dir": "./data",
        "chroma_collection": "counselor",
    },
    "embedding": {
        "model": "BAAI/bge-m3",
    },
}


REQUIRES_RESTART: dict[str, set[str]] = {
    # llm: all fields are hot-reloadable. `get_llm()` reads base_url /
    # model_name / timeout / api_key / temperature / ... from the singleton
    # on every request, and the startup hook re-applies admin DB overrides
    # on every process restart, so changes take effect without restart.
    "llm": set(),
    # retrieval: `get_retriever()` and `split()` read k / chunk_size /
    # chunk_overlap from the singleton at call time. Re-ingestion picks up
    # new chunk sizes immediately; existing chunks stay as-is.
    "retrieval": set(),
    # paths: chroma collection / data dir cannot be changed in-place without
    # rebuilding the collection — truly restart-required.
    "paths": {"documents_dir", "data_dir", "chroma_collection"},
    # embedding: SentenceTransformer instance is loaded once at first use and
    # cached. Changing the model name requires a restart.
    "embedding": {"model"},
}


# ---------- validation rules ----------

_RANGE_CHECKS: dict[tuple[str, str], tuple[float, float]] = {
    ("llm", "temperature"): (0.0, 2.0),
    ("llm", "max_tokens"): (1.0, 32768.0),
    ("llm", "timeout"): (5.0, 600.0),
    ("llm", "top_p"): (0.0, 1.0),
    ("llm", "frequency_penalty"): (-2.0, 2.0),
    ("llm", "presence_penalty"): (-2.0, 2.0),
    ("retrieval", "k"): (1.0, 50.0),
    ("retrieval", "chunk_size"): (50.0, 5000.0),
    ("retrieval", "chunk_overlap"): (0.0, 5000.0),
}

_INT_FIELDS: set[tuple[str, str]] = {
    ("llm", "max_tokens"), ("llm", "timeout"),
    ("retrieval", "k"), ("retrieval", "chunk_size"), ("retrieval", "chunk_overlap"),
}

_STR_FIELDS: set[tuple[str, str]] = {
    ("llm", "base_url"), ("llm", "model_name"), ("llm", "api_key"),
    ("paths", "documents_dir"), ("paths", "data_dir"), ("paths", "chroma_collection"),
    ("embedding", "model"),
}


class SettingsError(Exception):
    """Base class."""


class UnknownSectionError(SettingsError):
    pass


class InvalidFieldError(SettingsError):
    pass


def _validate_section_payload(section: str, payload: dict) -> None:
    known = DEFAULTS[section]
    for field, value in payload.items():
        if field not in known:
            raise InvalidFieldError(
                f"unknown field {section}.{field!r}"
            )
        key = (section, field)
        # Type checks
        if key in _INT_FIELDS:
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidFieldError(
                    f"{section}.{field} must be int, got {type(value).__name__}"
                )
        elif key in _STR_FIELDS:
            if not isinstance(value, str) or not value:
                raise InvalidFieldError(
                    f"{section}.{field} must be non-empty string"
                )
        else:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise InvalidFieldError(
                    f"{section}.{field} must be number, got {type(value).__name__}"
                )
        # Range checks
        if key in _RANGE_CHECKS:
            lo, hi = _RANGE_CHECKS[key]
            if not (lo <= float(value) <= hi):
                raise InvalidFieldError(
                    f"{section}.{field}={value} out of range [{lo}, {hi}]"
                )

    # Cross-field: chunk_overlap < chunk_size within retrieval.
    if section == "retrieval":
        if (
            "chunk_size" in payload or "chunk_overlap" in payload
        ):
            # Re-read stored + payload to evaluate the pair.
            current = dict(DEFAULTS["retrieval"])
            current.update(db_settings.get("retrieval") or {})
            current.update(payload)
            if current["chunk_overlap"] >= current["chunk_size"]:
                raise InvalidFieldError(
                    f"retrieval.chunk_overlap ({current['chunk_overlap']})"
                    f" must be < retrieval.chunk_size ({current['chunk_size']})"
                )


# ---------- public API ----------

def get_effective_settings() -> dict[str, dict]:
    """Return all 4 sections merged with defaults."""
    stored = db_settings.get_all()
    out: dict[str, dict] = {}
    for section in SECTIONS:
        merged = dict(DEFAULTS[section])
        merged.update(stored.get(section, {}))
        out[section] = merged
    return out


def update_settings(
    *, sections: dict, by_username: str
) -> tuple[dict, list[str]]:
    """Validate, persist, and return (new_sections, restart_required_fields).

    `restart_required_fields` is a list of "section.field" strings.

    Two-phase: validate every section first (building a pending map), then
    persist all. If any section fails validation, the whole request is
    rejected and nothing is written to the DB.
    """
    if not isinstance(sections, dict):
        raise InvalidFieldError("sections must be an object")
    # --- Phase 1: validate all sections, build pending map (no writes) ---
    pending: dict[str, dict] = {}
    restart: list[str] = []
    for section, payload in sections.items():
        if section not in SECTIONS:
            raise UnknownSectionError(f"unknown section {section!r}")
        if not isinstance(payload, dict):
            raise InvalidFieldError(f"{section} payload must be an object")
        _validate_section_payload(section, payload)
        # Merge with stored override (if any). No write happens here.
        existing = db_settings.get(section) or {}
        merged = dict(existing)
        merged.update(payload)
        pending[section] = merged
        # Tag restart-required fields that appear in this update.
        for field in payload.keys():
            if section in REQUIRES_RESTART and field in REQUIRES_RESTART[section]:
                restart.append(f"{section}.{field}")
    # --- Phase 2: persist all (no raises after this point) ---
    new_state: dict[str, dict] = {}
    for section, merged in pending.items():
        db_settings.set(section, merged, by_username)
        new_state[section] = merged
    return new_state, restart


__all__ = [
    "DEFAULTS",
    "InvalidFieldError",
    "REQUIRES_RESTART",
    "SECTIONS",
    "SettingsError",
    "UnknownSectionError",
    "get_effective_settings",
    "update_settings",
]