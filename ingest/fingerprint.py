# ingest/fingerprint.py
from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def should_skip(meta_entry: dict[str, Any] | None, path: str) -> bool:
    if not meta_entry:
        return False
    if not os.path.exists(path):
        return False
    if meta_entry.get("hash") != hash_file(path):
        return False
    # mtime 检查（容差 1s，避免文件系统精度差异）
    stat = os.stat(path)
    return abs(stat.st_mtime - float(meta_entry.get("mtime", 0))) < 1.0


@dataclass
class IndexMeta:
    path: str
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.files = data.get("files", {})
        self.failures = data.get("failures", [])

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"files": self.files, "failures": self.failures}, f,
                      ensure_ascii=False, indent=2)

    def get(self, file_path: str) -> dict[str, Any] | None:
        return self.files.get(file_path)

    def set(self, file_path: str, entry: dict[str, Any]) -> None:
        self.files[file_path] = entry
        self.save()

    def set_failed(self, file_path: str, error: str) -> None:
        self.failures.append({"path": file_path, "error": error})
        self.save()

    def failed(self) -> list[dict[str, str]]:
        return list(self.failures)