# app/admin/reindex.py
"""Wrap ingest.indexer.build_index with a process-local lock and last-result cache."""
from __future__ import annotations

import threading
import time
from typing import Any

from ingest.indexer import build_index

from storage.admin_db import kv


_REINDEX_LOCK = threading.Lock()


class ReindexBusyError(Exception):
    """Raised when reindex is already running."""


def run_reindex(*, force: bool = False) -> dict[str, Any]:
    """Run build_index under a process-local lock.

    Raises ReindexBusyError if another reindex is already running.
    Writes a summary to kv('last_reindex') on success.
    """
    if not _REINDEX_LOCK.acquire(blocking=False):
        raise ReindexBusyError("reindex already in progress")
    try:
        result = build_index(force=force)
    finally:
        _REINDEX_LOCK.release()

    summary = {
        "ts": time.time(),
        "force": force,
        "added": result.get("added", 0),
        "skipped": result.get("skipped", 0),
        "failed": result.get("failed", []),
    }
    kv.set("last_reindex", summary)
    return result


def get_last_reindex() -> dict | None:
    return kv.get("last_reindex")


__all__ = ["ReindexBusyError", "get_last_reindex", "run_reindex"]
