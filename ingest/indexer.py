# ingest/indexer.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from rag.loaders import SUFFIX_LOADERS, load as loader_load
from rag.splitter import split
from rag.retriever import get_chroma
from .fingerprint import IndexMeta, hash_file


SUPPORTED_EXTS = set(SUFFIX_LOADERS.keys())


def _documents_dir() -> str:
    return os.environ.get("DOCUMENTS_DIR", "./Documents")


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "./data")


def _meta_path() -> str:
    return os.path.join(_data_dir(), "index_meta.json")


def _iter_files(root: str) -> list[str]:
    p = Path(root)
    if not p.exists():
        return []
    return sorted(str(x) for x in p.rglob("*") if x.is_file())


def _process_one(path: str, meta: IndexMeta, *, force: bool) -> dict[str, Any]:
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        return {"status": "skipped", "path": path, "reason": f"ext {ext} unsupported"}

    entry = meta.get(path)
    if not force and entry and entry.get("hash") == hash_file(path):
        return {"status": "skipped", "path": path, "reason": "unchanged"}

    docs = loader_load(path)                            # 出错会抛
    if not docs:
        return {"status": "skipped", "path": path, "reason": "empty"}

    chunks = split(docs)
    if not chunks:
        return {"status": "skipped", "path": path, "reason": "no chunks"}

    try:
        get_chroma().add_documents(chunks)
    except Exception as exc:                             # noqa: BLE001
        # Direct dict mutation (no auto-save) — batched at end of build_index.
        meta.failures.append({"path": path, "error": f"chroma: {exc}"})
        return {"status": "failed", "path": path, "error": f"chroma: {exc}"}

    stat = Path(path).stat()
    # Direct dict mutation (no auto-save) — batched at end of build_index.
    meta.files[path] = {
        "hash": hash_file(path),
        "mtime": stat.st_mtime,
        "chunks": len(chunks),
    }
    return {"status": "added", "path": path, "chunks": len(chunks)}


def build_index(force: bool = False) -> dict[str, Any]:
    """扫描 DOCUMENTS_DIR，对每个文件判断是否需入索引。返回汇总。"""
    meta = IndexMeta(path=_meta_path())
    meta.load()

    result: dict[str, Any] = {"added": 0, "skipped": 0, "failed": [], "items": []}
    for path in _iter_files(_documents_dir()):
        try:
            item = _process_one(path, meta, force=force)
        except Exception as exc:                          # noqa: BLE001
            # Direct dict mutation (no auto-save) — batched at end of build_index.
            meta.failures.append({"path": path, "error": str(exc)})
            result["failed"].append({"path": path, "error": str(exc)})
            continue

        result["items"].append(item)
        if item["status"] == "added":
            result["added"] += 1
        elif item["status"] == "skipped":
            result["skipped"] += 1
        elif item["status"] == "failed":
            # Failed entry already appended to meta.failures inside _process_one.
            result["failed"].append(item)

    # Single disk write for the entire batch (avoids N-write storm).
    meta.save()
    result["meta_written"] = True
    return result
