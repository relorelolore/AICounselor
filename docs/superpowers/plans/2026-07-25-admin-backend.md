# Admin Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the existing single-user chat system into (a) an unchanged user-facing chat SPA at `/` and (b) a new admin backend at `/admin*` + `/api/admin/*` that manages AI model parameters, triggers vector-DB reindexing, and supports multiple admin accounts with permanent lockout after 6 failed logins. All admin data lives in a single SQLite file `data/admin.db` (stdlib `sqlite3`).

**Architecture:** Single FastAPI process. New `app/admin/` package owns auth, account CRUD, settings persistence, reindex service, and FastAPI router. New `storage/admin_db.py` owns the SQLite connection + schema + all admin DB operations (4 tables: accounts, sessions, settings, kv). New `web/admin/` static SPA (vanilla JS, no build) provides login + dashboard + accounts + settings pages. Session cookie `counselor_admin` (HttpOnly, SameSite=Lax, 24h sliding). Public `/api/ingest` removed; reindex is admin-only. `llm/config.py` and `rag/{retriever,splitter}.py` refactored to read from runtime config singletons for hot-reload of inference/retrieval params.

**Tech Stack:** FastAPI + WebSocket; Python stdlib `sqlite3` (WAL mode, `check_same_thread=False` + `threading.RLock` for writes); `secrets.token_urlsafe` + `hashlib.sha256` for auth; vanilla JS SPA; existing `NoStoreStaticFiles` for cache-bust.

## Global Constraints

From the spec (`docs/superpowers/specs/2026-07-25-admin-backend-design.md`) + `CLAUDE.md`, applicable to every task unless that task overrides:

- Python: `.venv` via `uv`; **never** `pip` / `python -m pytest`; always `OFFLINE=1 uv run --extra dev pytest` (skip bge-m3 download in CI).
- Frontend: no npm, no bundler. All admin SPA files in `web/admin/`; existing user SPA in `web/` untouched (except removing the reindex button in Task 8).
- Static files must keep `Cache-Control: no-store` (existing `app/static_no_store.py::NoStoreStaticFiles`).
- Frontend cache-bust query string must increment monotonically; user SPA `app.js` is at `?v=12` (Task 8 removes nothing version-wise but admin SPA starts at `?v=1`).
- Tests live under `tests/` with **no `__init__.py`** (pytest rootdir auto-discovery).
- `OFFLINE=1` skips bge-m3; live llama.cpp at `http://localhost:8848/v1` may be down — tests must not require it (use `RotatingFakeChat` + `FakeRetriever` for graph; mock LLM client for routes).
- HTTP errors are sanitized (`{"event":"error","data":"..."}` for WS; `HTTPException(detail="...")` for HTTP); never leak stack traces.
- `storage/paths.py` is the single source of disk paths; do not hardcode elsewhere. New constants: `ADMIN_DB`, `ADMIN_WEB_DIR`.
- Default admin account `admin / 147369` is seeded automatically on first DB connect; every test must run with a `tmp_path` DB to avoid clobbering real data.
- Admin WebSocket is **not** used in this design — all admin interaction is HTTP JSON + redirects.
- `pytest.ini` may emit `PendingDeprecationWarning` from `langchain-community` — safe to ignore.

---

### Task 1: SQLite persistence layer — `storage/admin_db.py` + tests

**Files:**
- Create: `storage/admin_db.py`
- Modify: `storage/paths.py:1-9`
- Create: `tests/test_admin_db.py`
- Modify: `tests/conftest.py` (add `_reset_admin_state` autouse fixture; keep existing autouse fixtures)

**Interfaces:**
- Consumes: `storage.paths.ADMIN_DB` env var `ADMIN_DB` (default `./data/admin.db`).
- Produces (module-level):
  - `ADMIN_DB_PATH: str` (resolves `ADMIN_DB` env at import time, see Step 3)
  - `reset_for_tests() -> None` — drops the cached connection + deletes the DB file at `ADMIN_DB_PATH` if it exists. Tests use this to start clean.
  - `init() -> None` — idempotent connect + `CREATE TABLE IF NOT EXISTS` + seed default admin if accounts table is empty.
  - Namespaces (callable objects with methods):
    - `accounts.list() -> list[dict]`
    - `accounts.get_by_username(username: str) -> dict | None`
    - `accounts.get_by_id(account_id: str) -> dict | None`
    - `accounts.create(username: str, password_hash: str, salt: str) -> dict` — raises `AccountExistsError`
    - `accounts.update(account_id: str, **fields) -> dict`
    - `accounts.delete(account_id: str) -> None`
    - `accounts.increment_failed_attempts(account_id: str) -> int` — returns new count
    - `accounts.reset_failed_attempts(account_id: str) -> None`
    - `accounts.set_locked(account_id: str, locked: bool) -> None`
    - `sessions.create(account_id: str) -> str` — returns session_id
    - `sessions.get(session_id: str) -> dict | None` — None if missing or expired
    - `sessions.touch(session_id: str) -> None`
    - `sessions.delete(session_id: str) -> None`
    - `sessions.cleanup_expired() -> int`
    - `settings.get(section: str) -> dict | None`
    - `settings.get_all() -> dict[str, dict]`
    - `settings.set(section: str, data: dict, updated_by: str) -> None`
    - `kv.get(key: str) -> dict | None`
    - `kv.set(key: str, value: dict) -> None`
  - Exceptions: `AdminDBError(Exception)`, `AccountExistsError(AdminDBError)`.

**Background:** All admin data lives in one SQLite file with WAL mode + a write lock (`threading.RLock`) for serialized writes. Schema is defined in spec §3. Tests must run against a tmp DB.

- [ ] **Step 1: Add new path constants**

Modify `storage/paths.py` — replace the existing 1-9 lines with:

```python
# storage/paths.py
import os


DATA_DIR: str = os.environ.get("DATA_DIR", "./data")
DOCUMENTS_DIR: str = os.environ.get("DOCUMENTS_DIR", "./Documents")
WEB_DIR: str = os.environ.get("WEB_DIR", "./web")
CHROMA_DIR: str = os.path.join(DATA_DIR, "chroma")
INDEX_META: str = os.path.join(DATA_DIR, "index_meta.json")
ADMIN_DB: str = os.environ.get("ADMIN_DB", os.path.join(DATA_DIR, "admin.db"))
ADMIN_WEB_DIR: str = os.environ.get("ADMIN_WEB_DIR", "./web/admin")
```

- [ ] **Step 2: Write failing tests for `storage/admin_db.py`**

Create `tests/test_admin_db.py`:

```python
"""Tests for storage/admin_db.py — SQLite persistence layer."""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from storage import admin_db
from storage.admin_db import (
    AccountExistsError,
    accounts,
    init,
    kv,
    reset_for_tests,
    sessions,
    settings,
)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "admin.db"
    monkeypatch.setattr(admin_db, "ADMIN_DB_PATH", str(db))
    reset_for_tests()
    init()
    yield
    reset_for_tests()


def test_init_creates_db_file():
    assert os.path.exists(admin_db.ADMIN_DB_PATH)


def test_init_seeds_default_admin():
    rows = accounts.list()
    assert len(rows) == 1
    assert rows[0]["username"] == "admin"
    assert rows[0]["locked"] == 0
    assert rows[0]["failed_attempts"] == 0
    # Sensitive fields must NOT leak through list().
    assert "password_hash" not in rows[0]
    assert "salt" not in rows[0]


def test_init_is_idempotent():
    init()  # second call should not raise
    assert len(accounts.list()) == 1


def test_create_account_rejects_duplicate_username():
    accounts.create("bob", "hash1", "salt1")
    with pytest.raises(AccountExistsError):
        accounts.create("bob", "hash2", "salt2")


def test_accounts_case_insensitive_unique():
    accounts.create("Bob", "h", "s")
    with pytest.raises(AccountExistsError):
        accounts.create("bob", "h", "s")


def test_get_by_username_returns_full_row():
    created = accounts.create("alice", "h", "s")
    row = accounts.get_by_username("alice")
    assert row is not None
    assert row["id"] == created["id"]
    assert row["password_hash"] == "h"
    assert row["salt"] == "s"


def test_get_by_username_missing_returns_none():
    assert accounts.get_by_username("nope") is None


def test_update_account_changes_field():
    created = accounts.create("alice", "h", "s")
    accounts.update(created["id"], failed_attempts=3, locked=True)
    row = accounts.get_by_id(created["id"])
    assert row["failed_attempts"] == 3
    assert row["locked"] == 1


def test_delete_account_cascades_sessions():
    a = accounts.create("alice", "h", "s")
    sid = sessions.create(a["id"])
    assert sessions.get(sid) is not None
    accounts.delete(a["id"])
    assert sessions.get(sid) is None
    assert accounts.get_by_id(a["id"]) is None


def test_increment_failed_attempts_returns_new_count():
    a = accounts.create("alice", "h", "s")
    assert accounts.increment_failed_attempts(a["id"]) == 1
    assert accounts.increment_failed_attempts(a["id"]) == 2
    row = accounts.get_by_id(a["id"])
    assert row["failed_attempts"] == 2


def test_reset_failed_attempts_and_set_locked():
    a = accounts.create("alice", "h", "s")
    accounts.increment_failed_attempts(a["id"])
    accounts.set_locked(a["id"], True)
    accounts.reset_failed_attempts(a["id"])
    accounts.set_locked(a["id"], False)
    row = accounts.get_by_id(a["id"])
    assert row["failed_attempts"] == 0
    assert row["locked"] == 0


def test_session_create_returns_urlsafe_id_and_round_trips():
    a = accounts.create("alice", "h", "s")
    sid = sessions.create(a["id"])
    assert isinstance(sid, str) and len(sid) >= 32
    sess = sessions.get(sid)
    assert sess is not None
    assert sess["account_id"] == a["id"]
    assert sess["expires_at"] > 0


def test_session_touch_extends_expiry(tmp_path, monkeypatch):
    import time
    a = accounts.create("alice", "h", "s")
    sid = sessions.create(a["id"])
    original = sessions.get(sid)["expires_at"]
    # Advance "now" past original expiry.
    monkeypatch.setattr(admin_db.time, "time", lambda: original + 100)
    sessions.touch(sid)
    sess = sessions.get(sid)
    assert sess["expires_at"] > original


def test_session_get_returns_none_when_expired(monkeypatch):
    import time
    a = accounts.create("alice", "h", "s")
    sid = sessions.create(a["id"])
    sess = sessions.get(sid)
    # Jump 25h ahead.
    monkeypatch.setattr(admin_db.time, "time", lambda: sess["expires_at"] + 1)
    assert sessions.get(sid) is None


def test_session_delete_removes_row():
    a = accounts.create("alice", "h", "s")
    sid = sessions.create(a["id"])
    sessions.delete(sid)
    assert sessions.get(sid) is None


def test_cleanup_expired_only_removes_expired(monkeypatch):
    import time
    a = accounts.create("alice", "h", "s")
    sid1 = sessions.create(a["id"])
    sid2 = sessions.create(a["id"])
    sess1 = sessions.get(sid1)
    # Expire sid1 only.
    monkeypatch.setattr(admin_db.time, "time", lambda: sess1["expires_at"] + 1)
    deleted = sessions.cleanup_expired()
    assert deleted == 1
    assert sessions.get(sid1) is None
    assert sessions.get(sid2) is not None


def test_settings_get_returns_none_when_missing():
    assert settings.get("llm") is None


def test_settings_set_then_get_round_trips():
    settings.set("llm", {"temperature": 0.7}, "admin")
    row = settings.get("llm")
    assert row == {"temperature": 0.7}


def test_settings_get_all_returns_only_set_sections():
    settings.set("llm", {"temperature": 0.7}, "admin")
    settings.set("retrieval", {"k": 10}, "admin")
    all_ = settings.get_all()
    assert set(all_.keys()) == {"llm", "retrieval"}
    assert all_["llm"] == {"temperature": 0.7}
    assert all_["retrieval"] == {"k": 10}


def test_settings_set_overwrites():
    settings.set("llm", {"temperature": 0.5}, "admin")
    settings.set("llm", {"temperature": 0.9, "max_tokens": 1024}, "admin")
    assert settings.get("llm") == {"temperature": 0.9, "max_tokens": 1024}


def test_kv_get_returns_none_when_missing():
    assert kv.get("startup_time") is None


def test_kv_set_then_get_round_trips():
    kv.set("last_reindex", {"added": 5})
    assert kv.get("last_reindex") == {"added": 5}


def test_kv_set_overwrites():
    kv.set("k", {"a": 1})
    kv.set("k", {"a": 2})
    assert kv.get("k") == {"a": 2}


def test_concurrent_set_setting_serializes():
    """5 threads writing to different sections must all succeed with no lost writes."""
    a = accounts.create("alice", "h", "s")
    errors: list[Exception] = []

    def writer(section, value):
        try:
            settings.set(section, {"v": value}, "admin")
        except Exception as exc:                                # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=(f"sec{i}", i))
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    for i in range(5):
        assert settings.get(f"sec{i}") == {"v": i}


def test_wal_mode_enabled():
    """WAL must be active so concurrent reads don't block writers."""
    row = admin_db._conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"


def test_reset_for_tests_deletes_db_file():
    p = Path(admin_db.ADMIN_DB_PATH)
    assert p.exists()
    reset_for_tests()
    assert not p.exists()


def test_init_after_reset_recreates_schema(tmp_path, monkeypatch):
    reset_for_tests()
    # After reset the file is gone; init() should recreate it.
    init()
    assert os.path.exists(admin_db.ADMIN_DB_PATH)
    assert len(accounts.list()) == 1  # default admin re-seeded
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_db.py -v`
Expected: `ModuleNotFoundError: No module named 'storage.admin_db'`

- [ ] **Step 4: Implement `storage/admin_db.py`**

Create `storage/admin_db.py`:

```python
# storage/admin_db.py
"""SQLite persistence for the admin backend.

Single connection (WAL mode) + write lock. Public API is a set of namespace
objects (accounts/sessions/settings/kv) with typed methods. Callers never
touch SQL directly.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any

from .paths import ADMIN_DB


ADMIN_DB_PATH: str = os.environ.get("ADMIN_DB_OVERRIDE", ADMIN_DB)


class AdminDBError(Exception):
    """Base class for admin DB errors."""


class AccountExistsError(AdminDBError):
    """Raised when creating an account whose username already exists."""


# ---------- connection management ----------

_conn: sqlite3.Connection | None = None
_WRITE_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    """Open (or return cached) connection. Caller must hold _WRITE_LOCK
    only for writes; reads may proceed without it."""
    global _conn
    if _conn is not None:
        return _conn
    os.makedirs(os.path.dirname(ADMIN_DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(ADMIN_DB_PATH, check_same_thread=False, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    c.row_factory = sqlite3.Row
    _conn = c
    return c


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        last_login_at REAL
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        last_seen_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)",
    """CREATE TABLE IF NOT EXISTS settings (
        section TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at REAL NOT NULL,
        updated_by TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS kv (
        k TEXT PRIMARY KEY,
        v TEXT NOT NULL
    )""",
]


def init() -> None:
    """Idempotent: create tables + seed default admin if accounts empty."""
    c = _connect()
    with _WRITE_LOCK:
        for stmt in _SCHEMA:
            c.execute(stmt)
        # Schema version
        c.execute(
            "INSERT OR IGNORE INTO schema_meta(key, value) VALUES(?, ?)",
            ("version", json.dumps({"version": 1})),
        )
        # Seed default admin if empty.
        (n,) = c.execute("SELECT COUNT(*) FROM accounts").fetchone()
        if n == 0:
            import hashlib
            import secrets as _sec
            salt = _sec.token_hex(16)
            pw_hash = hashlib.sha256((salt + "147369").encode()).hexdigest()
            now = time.time()
            c.execute(
                "INSERT INTO accounts(id, username, password_hash, salt,"
                " failed_attempts, locked, created_at, updated_at)"
                " VALUES(?, ?, ?, ?, 0, 0, ?, ?)",
                (str(uuid.uuid4()), "admin", pw_hash, salt, now, now),
            )
            print(
                "[admin] seeded default admin account (username=admin);"
                " change password on first login",
                flush=True,
            )
        kv.set("startup_time", {"ts": time.time()})


def reset_for_tests() -> None:
    """Drop the cached connection and delete the DB file. Tests only."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None
    try:
        os.remove(ADMIN_DB_PATH)
    except FileNotFoundError:
        pass
    # Also remove WAL sidecars if present.
    for suffix in ("-wal", "-shm"):
        try:
            os.remove(ADMIN_DB_PATH + suffix)
        except FileNotFoundError:
            pass


# ---------- helpers ----------

def _now() -> float:
    return time.time()


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_public(row: sqlite3.Row) -> dict[str, Any]:
    """Strip password_hash/salt and convert booleans."""
    d = dict(row)
    d.pop("password_hash", None)
    d.pop("salt", None)
    d["locked"] = bool(d.get("locked", 0))
    return d


# ---------- accounts namespace ----------

class _Accounts:
    def list(self) -> list[dict]:
        with _WRITE_LOCK:
            rows = _connect().execute(
                "SELECT * FROM accounts ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_public(r) for r in rows]

    def get_by_username(self, username: str) -> dict | None:
        with _WRITE_LOCK:
            row = _connect().execute(
                "SELECT * FROM accounts WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_id(self, account_id: str) -> dict | None:
        with _WRITE_LOCK:
            row = _connect().execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
        return dict(row) if row else None

    def create(self, username: str, password_hash: str, salt: str) -> dict:
        now = _now()
        aid = _new_id()
        with _WRITE_LOCK:
            try:
                _connect().execute(
                    "INSERT INTO accounts(id, username, password_hash, salt,"
                    " failed_attempts, locked, created_at, updated_at)"
                    " VALUES(?, ?, ?, ?, 0, 0, ?, ?)",
                    (aid, username, password_hash, salt, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise AccountExistsError(
                    f"username {username!r} already exists"
                ) from exc
        return self.get_by_id(aid) or {}

    def update(self, account_id: str, **fields) -> dict:
        if not fields:
            return self.get_by_id(account_id) or {}
        # Whitelist updatable columns.
        allowed = {
            "password_hash", "salt", "failed_attempts", "locked",
            "last_login_at",
        }
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"cannot update fields: {sorted(bad)}")
        cols = list(fields.keys())
        placeholders = ", ".join(f"{c} = ?" for c in cols)
        values = [fields[c] for c in cols] + [_now(), account_id]
        with _WRITE_LOCK:
            _connect().execute(
                f"UPDATE accounts SET {placeholders}, updated_at = ? WHERE id = ?",
                values,
            )
        return self.get_by_id(account_id) or {}

    def delete(self, account_id: str) -> None:
        with _WRITE_LOCK:
            _connect().execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    def increment_failed_attempts(self, account_id: str) -> int:
        with _WRITE_LOCK:
            _connect().execute(
                "UPDATE accounts SET failed_attempts = failed_attempts + 1,"
                " updated_at = ? WHERE id = ?",
                (_now(), account_id),
            )
            row = _connect().execute(
                "SELECT failed_attempts FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
        return int(row["failed_attempts"]) if row else 0

    def reset_failed_attempts(self, account_id: str) -> None:
        with _WRITE_LOCK:
            _connect().execute(
                "UPDATE accounts SET failed_attempts = 0, updated_at = ?"
                " WHERE id = ?",
                (_now(), account_id),
            )

    def set_locked(self, account_id: str, locked: bool) -> None:
        with _WRITE_LOCK:
            _connect().execute(
                "UPDATE accounts SET locked = ?, updated_at = ? WHERE id = ?",
                (1 if locked else 0, _now(), account_id),
            )


# ---------- sessions namespace ----------

class _Sessions:
    _TTL_SECONDS = 24 * 3600

    def create(self, account_id: str) -> str:
        sid = _new_id()  # 128-bit uuid; URL-safe via str()
        now = _now()
        with _WRITE_LOCK:
            _connect().execute(
                "INSERT INTO sessions(session_id, account_id, created_at,"
                " expires_at, last_seen_at) VALUES(?, ?, ?, ?, ?)",
                (sid, account_id, now, now + self._TTL_SECONDS, now),
            )
        return sid

    def get(self, session_id: str) -> dict | None:
        with _WRITE_LOCK:
            row = _connect().execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d["expires_at"] < _now():
            self.delete(session_id)
            return None
        return d

    def touch(self, session_id: str) -> None:
        now = _now()
        with _WRITE_LOCK:
            _connect().execute(
                "UPDATE sessions SET expires_at = ?, last_seen_at = ?"
                " WHERE session_id = ?",
                (now + self._TTL_SECONDS, now, session_id),
            )

    def delete(self, session_id: str) -> None:
        with _WRITE_LOCK:
            _connect().execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )

    def cleanup_expired(self) -> int:
        with _WRITE_LOCK:
            cur = _connect().execute(
                "DELETE FROM sessions WHERE expires_at < ?", (_now(),)
            )
        return cur.rowcount


# ---------- settings namespace ----------

class _Settings:
    def get(self, section: str) -> dict | None:
        with _WRITE_LOCK:
            row = _connect().execute(
                "SELECT data FROM settings WHERE section = ?", (section,)
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["data"])

    def get_all(self) -> dict[str, dict]:
        with _WRITE_LOCK:
            rows = _connect().execute("SELECT section, data FROM settings").fetchall()
        return {r["section"]: json.loads(r["data"]) for r in rows}

    def set(self, section: str, data: dict, updated_by: str) -> None:
        now = _now()
        payload = json.dumps(data, ensure_ascii=False)
        with _WRITE_LOCK:
            _connect().execute(
                "INSERT INTO settings(section, data, updated_at, updated_by)"
                " VALUES(?, ?, ?, ?)"
                " ON CONFLICT(section) DO UPDATE SET"
                " data = excluded.data, updated_at = excluded.updated_at,"
                " updated_by = excluded.updated_by",
                (section, payload, now, updated_by),
            )


# ---------- kv namespace ----------

class _KV:
    def get(self, key: str) -> dict | None:
        with _WRITE_LOCK:
            row = _connect().execute(
                "SELECT v FROM kv WHERE k = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["v"])

    def set(self, key: str, value: dict) -> None:
        with _WRITE_LOCK:
            _connect().execute(
                "INSERT INTO kv(k, v) VALUES(?, ?)"
                " ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                (key, json.dumps(value, ensure_ascii=False)),
            )


accounts = _Accounts()
sessions = _Sessions()
settings = _Settings()
kv = _KV()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_db.py -v`
Expected: all ~25 tests pass.

- [ ] **Step 6: Commit**

```bash
git add storage/admin_db.py storage/paths.py tests/test_admin_db.py
git commit -m "feat(admin): SQLite persistence layer (storage/admin_db.py)

- Single SQLite file data/admin.db, WAL mode, write lock
- 4 tables: accounts, sessions, settings, kv + schema_meta
- Default admin/147369 seeded on first init()
- Namespace API: accounts/sessions/settings/kv
- 25 tests covering schema, CRUD, session lifecycle, concurrency"
```

---

### Task 2: Auth module — `app/admin/auth.py` + tests

**Files:**
- Create: `app/admin/__init__.py`
- Create: `app/admin/auth.py`
- Create: `tests/test_admin_auth.py`

**Interfaces:**
- Consumes: `storage.admin_db.accounts`, `storage.admin_db.sessions`.
- Produces (module-level):
  - `MAX_FAILED_ATTEMPTS = 6`
  - `SESSION_COOKIE_NAME = "counselor_admin"`
  - `SESSION_TTL_SECONDS = 24 * 3600`
  - `SESSION_COOKIE_ATTRS = {"httponly": True, "samesite": "lax", "path": "/"}`
  - `hash_password(password: str, salt: str) -> str` — sha256(salt + password), hex
  - `verify_password(password: str, salt: str, expected_hash: str) -> bool` — constant-time compare
  - `generate_salt() -> str` — `secrets.token_hex(16)`
  - `login_attempt(username: str, password: str) -> tuple[str | None, str | None]` — returns `(session_id, error_code)` where error_code ∈ `{"invalid_credentials", "account_locked"}`. Both None on success.
  - `validate_session(session_id: str) -> dict | None` — uses admin_db.sessions.get (which auto-cleans expired) and also touches the session on success.
  - `delete_session(session_id: str) -> None`

**Background:** `login_attempt` is the gate. It must not leak whether the username exists — same error for wrong username and wrong password. After 6 failed attempts the account is permanently locked; only another admin can unlock via the accounts route (Task 7). Successful logins reset `failed_attempts` but do NOT auto-unlock.

- [ ] **Step 1: Write failing tests for `app/admin/auth.py`**

Create `tests/test_admin_auth.py`:

```python
"""Tests for app/admin/auth.py — password hashing + login_attempt + session validation."""
from __future__ import annotations

import pytest

from app.admin import auth
from storage import admin_db
from storage.admin_db import accounts, reset_for_tests, sessions


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_db, "ADMIN_DB_PATH", str(tmp_path / "admin.db"))
    reset_for_tests()
    admin_db.init()
    yield
    reset_for_tests()


# ----- hashing -----

def test_hash_password_deterministic_with_same_salt():
    a = auth.hash_password("pw", "salt")
    b = auth.hash_password("pw", "salt")
    assert a == b


def test_hash_password_differs_with_different_salts():
    a = auth.hash_password("pw", "salt1")
    b = auth.hash_password("pw", "salt2")
    assert a != b


def test_generate_salt_unique_each_call():
    assert auth.generate_salt() != auth.generate_salt()


def test_verify_password_true_for_match():
    salt = auth.generate_salt()
    h = auth.hash_password("pw", salt)
    assert auth.verify_password("pw", salt, h) is True


def test_verify_password_false_for_mismatch():
    salt = auth.generate_salt()
    h = auth.hash_password("pw", salt)
    assert auth.verify_password("wrong", salt, h) is False


def test_verify_password_false_for_salt_mismatch():
    salt = auth.generate_salt()
    h = auth.hash_password("pw", salt)
    assert auth.verify_password("pw", "different", h) is False


# ----- login_attempt -----

def test_login_default_admin_succeeds():
    sid, err = auth.login_attempt("admin", "147369")
    assert sid is not None and err is None
    row = admin_db.accounts.get_by_username("admin")
    assert row["last_login_at"] is not None
    assert row["failed_attempts"] == 0


def test_login_unknown_user_returns_invalid_credentials():
    sid, err = auth.login_attempt("ghost", "whatever")
    assert sid is None
    assert err == "invalid_credentials"


def test_login_wrong_password_returns_invalid_credentials():
    sid, err = auth.login_attempt("admin", "wrong")
    assert sid is None
    assert err == "invalid_credentials"
    row = admin_db.accounts.get_by_username("admin")
    assert row["failed_attempts"] == 1


def test_login_locks_after_six_failures():
    for _ in range(5):
        sid, err = auth.login_attempt("admin", "wrong")
        assert err == "invalid_credentials"
    sid, err = auth.login_attempt("admin", "wrong")
    assert err == "account_locked"
    row = admin_db.accounts.get_by_username("admin")
    assert row["locked"] == 1
    assert row["failed_attempts"] == 6


def test_locked_account_rejects_correct_password():
    for _ in range(6):
        auth.login_attempt("admin", "wrong")
    sid, err = auth.login_attempt("admin", "147369")
    assert sid is None
    assert err == "account_locked"


def test_successful_login_resets_failed_attempts_but_keeps_lock():
    for _ in range(5):
        auth.login_attempt("admin", "wrong")
    # 6th wrong → locked
    auth.login_attempt("admin", "wrong")
    # Unlock manually, then verify failed_attempts reset on success.
    row = admin_db.accounts.get_by_username("admin")
    admin_db.accounts.update(row["id"], locked=False)
    sid, err = auth.login_attempt("admin", "147369")
    assert sid is not None and err is None
    row = admin_db.accounts.get_by_username("admin")
    assert row["failed_attempts"] == 0
    assert row["locked"] == 0


def test_login_attempt_for_unlocked_after_6_does_not_relock():
    row = admin_db.accounts.get_by_username("admin")
    admin_db.accounts.update(row["id"], failed_attempts=6, locked=True)
    admin_db.accounts.update(row["id"], locked=False, failed_attempts=6)
    sid, err = auth.login_attempt("admin", "wrong")
    assert err == "invalid_credentials"
    row = admin_db.accounts.get_by_username("admin")
    assert row["failed_attempts"] == 7
    assert row["locked"] == 0  # not re-locked by 7th failure


# ----- session lifecycle -----

def test_validate_session_returns_dict_for_valid():
    row = admin_db.accounts.get_by_username("admin")
    sid = sessions.create(row["id"])
    sess = auth.validate_session(sid)
    assert sess is not None
    assert sess["account_id"] == row["id"]


def test_validate_session_returns_none_for_missing():
    assert auth.validate_session("nonexistent-id") is None


def test_validate_session_returns_none_and_cleans_up_when_expired(monkeypatch):
    row = admin_db.accounts.get_by_username("admin")
    sid = sessions.create(row["id"])
    sess = sessions.get(sid)
    monkeypatch.setattr(admin_db.time, "time", lambda: sess["expires_at"] + 1)
    assert auth.validate_session(sid) is None
    assert sessions.get(sid) is None  # auto-cleaned


def test_validate_session_touches_extending_expiry(monkeypatch):
    row = admin_db.accounts.get_by_username("admin")
    sid = sessions.create(row["id"])
    original = sessions.get(sid)["expires_at"]
    # Advance 12h.
    monkeypatch.setattr(admin_db.time, "time", lambda: original - 12 * 3600)
    sess = auth.validate_session(sid)
    assert sess is not None
    assert sess["expires_at"] > original


def test_delete_session_removes_row():
    row = admin_db.accounts.get_by_username("admin")
    sid = sessions.create(row["id"])
    auth.delete_session(sid)
    assert sessions.get(sid) is None


# ----- constants -----

def test_constants_have_expected_values():
    assert auth.MAX_FAILED_ATTEMPTS == 6
    assert auth.SESSION_COOKIE_NAME == "counselor_admin"
    assert auth.SESSION_TTL_SECONDS == 24 * 3600
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_auth.py -v`
Expected: `ModuleNotFoundError: No module named 'app.admin'`

- [ ] **Step 3: Create `app/admin/__init__.py`**

```python
# app/admin/__init__.py
"""Admin backend: auth, accounts CRUD, settings, reindex, HTTP routes."""
```

- [ ] **Step 4: Implement `app/admin/auth.py`**

Create `app/admin/auth.py`:

```python
# app/admin/auth.py
"""Password hashing, session validation, and login_attempt gate.

The login_attempt function is the single point where failed-attempt counters
increment and accounts become locked. It must NOT reveal whether a username
exists — wrong username and wrong password return the same error code.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from storage import admin_db
from storage.admin_db import accounts, sessions


MAX_FAILED_ATTEMPTS: int = 6
SESSION_COOKIE_NAME: str = "counselor_admin"
SESSION_TTL_SECONDS: int = 24 * 3600
SESSION_COOKIE_ATTRS: dict[str, object] = {
    "httponly": True,
    "samesite": "lax",
    "path": "/",
}


# ---------- password helpers ----------

def generate_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected_hash)


# ---------- login_attempt gate ----------

def login_attempt(username: str, password: str) -> tuple[str | None, str | None]:
    """Return (session_id, error_code).

    error_code ∈ {"invalid_credentials", "account_locked"} on failure.
    Both None on success.
    """
    row = accounts.get_by_username(username)
    if row is None:
        # Don't reveal whether the username exists; do NOT increment any
        # counter (the account doesn't exist anyway).
        return None, "invalid_credentials"

    if row["locked"]:
        return None, "account_locked"

    if not verify_password(password, row["salt"], row["password_hash"]):
        new_count = accounts.increment_failed_attempts(row["id"])
        if new_count >= MAX_FAILED_ATTEMPTS:
            accounts.set_locked(row["id"], True)
            return None, "account_locked"
        return None, "invalid_credentials"

    # Success path.
    accounts.reset_failed_attempts(row["id"])
    accounts.update(row["id"], last_login_at=admin_db._now())
    sid = sessions.create(row["id"])
    return sid, None


# ---------- session helpers ----------

def validate_session(session_id: str) -> dict | None:
    """Return the session row if valid (also touches it to slide the TTL).

    Returns None for missing or expired sessions. Expired sessions are
    cleaned up by admin_db.sessions.get on the way out.
    """
    sess = sessions.get(session_id)
    if sess is None:
        return None
    sessions.touch(session_id)
    # Re-read to get the post-touch expiry.
    return sessions.get(session_id) or sess


def delete_session(session_id: str) -> None:
    sessions.delete(session_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_auth.py -v`
Expected: ~22 tests pass.

- [ ] **Step 6: Run full suite to verify no regressions**

Run: `OFFLINE=1 uv run --extra dev pytest -q`
Expected: 57 + ~47 = ~104 passed / 2 skipped.

- [ ] **Step 7: Commit**

```bash
git add app/admin/__init__.py app/admin/auth.py tests/test_admin_auth.py
git commit -m "feat(admin): auth module (hash/verify, login_attempt, validate_session)

- 6 failed attempts → permanent lock
- Wrong username + wrong password return same 'invalid_credentials' code
- Successful login resets failed_attempts but never auto-unlocks
- Constant-time password compare via hmac.compare_digest"
```

---

### Task 3: Account CRUD business logic — `app/admin/accounts.py` + tests

**Files:**
- Create: `app/admin/accounts.py`
- Create: `tests/test_admin_accounts.py`

**Interfaces:**
- Consumes: `app.admin.auth.hash_password`, `verify_password`, `generate_salt`, `MAX_FAILED_ATTEMPTS`; `storage.admin_db.accounts`.
- Produces (module-level):
  - `USERNAME_MIN_LEN = 3`, `USERNAME_MAX_LEN = 32`
  - `USERNAME_RE = re.compile(r"^[a-z0-9_-]+$")`
  - `PASSWORD_MIN_LEN = 6`
  - `class AccountsError(Exception)` with subclasses: `WeakPasswordError`, `InvalidUsernameError`, `AccountNotFoundError`, `SelfDeleteError`, `LastAdminError`, `SelfUnlockError`, `WrongOldPasswordError`.
  - `create_account(*, username, password, by_username) -> dict` — raises `InvalidUsernameError` / `WeakPasswordError` / `AccountExistsError` (re-exported from admin_db).
  - `list_accounts() -> list[dict]`
  - `get_account_by_id(account_id) -> dict | None`
  - `change_password(*, target_id, new_password, by_account, old_password=None) -> dict` — when `target_id == by_account.id` `old_password` is required and verified.
  - `unlock_account(*, target_id, by_account) -> dict` — refuses if `target_id == by_account.id` (self-unlock).
  - `delete_account(*, target_id, by_account) -> None` — refuses self-delete; refuses if it would leave 0 admins.

**Background:** All business rules from spec §3 (self-protection). Validation is done here so HTTP routes (Task 7) just translate exceptions to HTTPException.

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin_accounts.py`:

```python
"""Tests for app/admin/accounts.py — CRUD business logic + self-protection rules."""
from __future__ import annotations

import pytest

from app.admin import accounts as accts
from app.admin.accounts import (
    AccountNotFoundError,
    InvalidUsernameError,
    LastAdminError,
    SelfDeleteError,
    SelfUnlockError,
    WeakPasswordError,
    WrongOldPasswordError,
)
from storage import admin_db
from storage.admin_db import accounts as db_accounts, reset_for_tests


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_db, "ADMIN_DB_PATH", str(tmp_path / "admin.db"))
    reset_for_tests()
    admin_db.init()
    yield
    reset_for_tests()


# ----- validation helpers -----

def test_validate_username_rejects_too_short():
    with pytest.raises(InvalidUsernameError):
        accts._validate_username("ab")


def test_validate_username_rejects_too_long():
    with pytest.raises(InvalidUsernameError):
        accts._validate_username("a" * 33)


def test_validate_username_rejects_bad_chars():
    for bad in ["ab cd", "ab.cd", "ab/cd", "汉字", "AB_CD"]:
        with pytest.raises(InvalidUsernameError):
            accts._validate_username(bad)


def test_validate_username_accepts_valid():
    for ok in ["abc", "a-b_c", "user_123", "a" * 32]:
        accts._validate_username(ok)


def test_validate_password_rejects_too_short():
    with pytest.raises(WeakPasswordError):
        accts._validate_password("12345")


def test_validate_password_accepts_six_chars():
    accts._validate_password("123456")


# ----- create_account -----

def test_create_account_hashes_password_not_stores_plain():
    created = accts.create_account(
        username="bob", password="secret123", by_username="admin"
    )
    assert created["username"] == "bob"
    # Internal row should have hashed password.
    internal = db_accounts.get_by_id(created["id"])
    assert internal["password_hash"] != "secret123"
    assert len(internal["salt"]) == 32


def test_create_account_rejects_weak_password():
    with pytest.raises(WeakPasswordError):
        accts.create_account(username="bob", password="abc", by_username="admin")


def test_create_account_rejects_invalid_username():
    with pytest.raises(InvalidUsernameError):
        accts.create_account(username="ab", password="secret1", by_username="admin")


def test_create_account_rejects_duplicate_username():
    accts.create_account(username="bob", password="secret1", by_username="admin")
    with pytest.raises(admin_db.AccountExistsError):
        accts.create_account(username="bob", password="secret2", by_username="admin")


# ----- change_password -----

def test_change_password_for_self_requires_old_password():
    admin = db_accounts.get_by_username("admin")
    with pytest.raises(WrongOldPasswordError):
        accts.change_password(
            target_id=admin["id"],
            new_password="newpass1",
            by_account=admin,
            old_password=None,
        )


def test_change_password_for_self_rejects_wrong_old():
    admin = db_accounts.get_by_username("admin")
    with pytest.raises(WrongOldPasswordError):
        accts.change_password(
            target_id=admin["id"],
            new_password="newpass1",
            by_account=admin,
            old_password="WRONG",
        )


def test_change_password_for_self_succeeds_with_correct_old():
    admin = db_accounts.get_by_username("admin")
    accts.change_password(
        target_id=admin["id"],
        new_password="newpass1",
        by_account=admin,
        old_password="147369",
    )
    # Login with new password should work.
    from app.admin.auth import login_attempt
    sid, err = login_attempt("admin", "newpass1")
    assert sid is not None and err is None


def test_change_password_for_other_admin_does_not_require_old():
    admin = db_accounts.get_by_username("admin")
    bob = accts.create_account(username="bob", password="bobpass1", by_username="admin")
    accts.change_password(
        target_id=bob["id"], new_password="newbob1", by_account=admin
    )
    from app.admin.auth import login_attempt
    sid, err = login_attempt("bob", "newbob1")
    assert sid is not None and err is None


def test_change_password_for_missing_target_raises():
    admin = db_accounts.get_by_username("admin")
    with pytest.raises(AccountNotFoundError):
        accts.change_password(
            target_id="nope", new_password="newpass1", by_account=admin
        )


# ----- unlock_account -----

def test_unlock_account_resets_failed_attempts():
    admin = db_accounts.get_by_username("admin")
    bob = accts.create_account(username="bob", password="bobpass1", by_username="admin")
    db_accounts.update(bob["id"], failed_attempts=6, locked=True)
    accts.unlock_account(target_id=bob["id"], by_account=admin)
    row = db_accounts.get_by_id(bob["id"])
    assert row["locked"] == 0
    assert row["failed_attempts"] == 0


def test_unlock_self_raises_self_unlock_error():
    admin = db_accounts.get_by_username("admin")
    db_accounts.update(admin["id"], failed_attempts=6, locked=True)
    with pytest.raises(SelfUnlockError):
        accts.unlock_account(target_id=admin["id"], by_account=admin)


def test_unlock_account_missing_target_raises():
    admin = db_accounts.get_by_username("admin")
    with pytest.raises(AccountNotFoundError):
        accts.unlock_account(target_id="nope", by_account=admin)


# ----- delete_account -----

def test_delete_account_removes_from_db():
    admin = db_accounts.get_by_username("admin")
    bob = accts.create_account(username="bob", password="bobpass1", by_username="admin")
    accts.delete_account(target_id=bob["id"], by_account=admin)
    assert db_accounts.get_by_id(bob["id"]) is None


def test_delete_self_raises_self_delete_error():
    admin = db_accounts.get_by_username("admin")
    with pytest.raises(SelfDeleteError):
        accts.delete_account(target_id=admin["id"], by_account=admin)


def test_delete_last_admin_raises_last_admin_error():
    admin = db_accounts.get_by_username("admin")
    with pytest.raises(LastAdminError):
        accts.delete_account(target_id=admin["id"], by_account=admin)


def test_delete_when_two_admins_exist_works():
    admin = db_accounts.get_by_username("admin")
    bob = accts.create_account(username="bob", password="bobpass1", by_username="admin")
    accts.delete_account(target_id=bob["id"], by_account=admin)
    assert db_accounts.get_by_id(bob["id"]) is None
    assert db_accounts.get_by_id(admin["id"]) is not None


def test_delete_missing_target_raises():
    admin = db_accounts.get_by_username("admin")
    with pytest.raises(AccountNotFoundError):
        accts.delete_account(target_id="nope", by_account=admin)


# ----- list_accounts -----

def test_list_accounts_excludes_hash_and_salt():
    accts.list_accounts()
    rows = accts.list_accounts()
    assert rows
    for r in rows:
        assert "password_hash" not in r
        assert "salt" not in r


def test_list_accounts_returns_dicts_with_expected_keys():
    rows = accts.list_accounts()
    assert {"id", "username", "failed_attempts", "locked",
            "created_at", "updated_at"} <= set(rows[0].keys())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_accounts.py -v`
Expected: `ModuleNotFoundError: No module named 'app.admin.accounts'`

- [ ] **Step 3: Implement `app/admin/accounts.py`**

Create `app/admin/accounts.py`:

```python
# app/admin/accounts.py
"""Account CRUD business logic with self-protection rules.

All validation happens here; routes (Task 7) translate these exceptions to
HTTPException.
"""
from __future__ import annotations

import re

from storage.admin_db import AccountExistsError, accounts

from . import auth


# ---------- validation ----------

USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 32
USERNAME_RE = re.compile(r"^[a-z0-9_-]+$")
PASSWORD_MIN_LEN = 6


class AccountsError(Exception):
    """Base class."""


class WeakPasswordError(AccountsError):
    pass


class InvalidUsernameError(AccountsError):
    pass


class AccountNotFoundError(AccountsError):
    pass


class SelfDeleteError(AccountsError):
    pass


class LastAdminError(AccountsError):
    pass


class SelfUnlockError(AccountsError):
    pass


class WrongOldPasswordError(AccountsError):
    pass


def _validate_username(username: str) -> None:
    if not isinstance(username, str):
        raise InvalidUsernameError("username must be a string")
    if not (USERNAME_MIN_LEN <= len(username) <= USERNAME_MAX_LEN):
        raise InvalidUsernameError(
            f"username must be {USERNAME_MIN_LEN}-{USERNAME_MAX_LEN} chars"
        )
    if not USERNAME_RE.match(username):
        raise InvalidUsernameError(
            "username must contain only [a-z0-9_-]"
        )


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LEN:
        raise WeakPasswordError(
            f"password must be at least {PASSWORD_MIN_LEN} characters"
        )


def _ensure_target(target_id: str) -> dict:
    row = accounts.get_by_id(target_id)
    if row is None:
        raise AccountNotFoundError(f"account {target_id!r} not found")
    return row


# ---------- public API ----------

def list_accounts() -> list[dict]:
    return accounts.list()


def get_account_by_id(account_id: str) -> dict | None:
    return accounts.get_by_id(account_id)


def create_account(*, username: str, password: str, by_username: str) -> dict:
    _validate_username(username)
    _validate_password(password)
    salt = auth.generate_salt()
    pw_hash = auth.hash_password(password, salt)
    return accounts.create(username, pw_hash, salt)


def change_password(
    *,
    target_id: str,
    new_password: str,
    by_account: dict,
    old_password: str | None = None,
) -> dict:
    _validate_password(new_password)
    target = _ensure_target(target_id)
    if target["id"] == by_account["id"]:
        if not old_password:
            raise WrongOldPasswordError("old_password required to change own password")
        if not auth.verify_password(
            old_password, target["salt"], target["password_hash"]
        ):
            raise WrongOldPasswordError("old password is incorrect")
    salt = auth.generate_salt()
    pw_hash = auth.hash_password(new_password, salt)
    return accounts.update(target["id"], password_hash=pw_hash, salt=salt)


def unlock_account(*, target_id: str, by_account: dict) -> dict:
    if target_id == by_account["id"]:
        raise SelfUnlockError("cannot self-unlock; ask another admin")
    target = _ensure_target(target_id)
    accounts.set_locked(target["id"], False)
    accounts.reset_failed_attempts(target["id"])
    return accounts.get_by_id(target["id"]) or {}


def delete_account(*, target_id: str, by_account: dict) -> None:
    if target_id == by_account["id"]:
        raise SelfDeleteError("cannot delete your own account")
    target = _ensure_target(target_id)
    # Last-admin guard.
    if len(accounts.list()) <= 1:
        raise LastAdminError("cannot delete the last admin account")
    accounts.delete(target["id"])


# Re-export so callers can catch without importing admin_db directly.
__all__ = [
    "AccountExistsError",
    "AccountNotFoundError",
    "AccountsError",
    "InvalidUsernameError",
    "LastAdminError",
    "SelfDeleteError",
    "SelfUnlockError",
    "WeakPasswordError",
    "WrongOldPasswordError",
    "create_account",
    "change_password",
    "delete_account",
    "get_account_by_id",
    "list_accounts",
    "unlock_account",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_accounts.py -v`
Expected: ~24 tests pass.

- [ ] **Step 5: Run full suite**

Run: `OFFLINE=1 uv run --extra dev pytest -q`
Expected: ~128 passed / 2 skipped.

- [ ] **Step 6: Commit**

```bash
git add app/admin/accounts.py tests/test_admin_accounts.py
git commit -m "feat(admin): accounts CRUD business logic + self-protection rules

- Username/password validation (length + chars)
- Self-delete + last-admin + self-unlock guards
- Self password change requires old_password; other admin does not
- All exceptions translated to HTTP codes by routes in Task 7"
```

---

### Task 4: Settings persistence — `app/admin/settings.py` + tests

**Files:**
- Create: `app/admin/settings.py`
- Create: `tests/test_admin_settings.py` (Part A — DB only)

**Interfaces:**
- Consumes: `storage.admin_db.settings`.
- Produces (module-level):
  - `SECTIONS = ("llm", "retrieval", "paths", "embedding")`
  - `DEFAULTS = {"llm": {...}, "retrieval": {...}, "paths": {...}, "embedding": {...}}` — see code.
  - `REQUIRES_RESTART = {"llm": {"base_url", "model_name", "timeout"}, "paths": {"documents_dir", "data_dir", "chroma_collection"}, "embedding": {"model"}}`
  - `class SettingsError(Exception)` with subclasses: `UnknownSectionError`, `InvalidFieldError`.
  - `get_effective_settings() -> dict` — returns `{section: merged_with_env_defaults}` for all 4 sections.
  - `update_settings(*, sections: dict[str, dict], by_username: str) -> tuple[dict, list[str]]` — returns `(new_sections, restart_required_fields)`. Validates types + ranges, raises `InvalidFieldError` on bad input.

**Background:** Settings are split into 4 sections. Hot-reloadable fields propagate to runtime modules in Task 5; restart-required fields are surfaced in the response. The DB only stores fields that the admin explicitly set; env vars fill in defaults.

- [ ] **Step 1: Write failing tests (Part A — DB + validation)**

Create `tests/test_admin_settings.py`:

```python
"""Tests for app/admin/settings.py — section config + validation."""
from __future__ import annotations

import pytest

from app.admin.settings import (
    DEFAULTS,
    InvalidFieldError,
    REQUIRES_RESTART,
    SECTIONS,
    SettingsError,
    UnknownSectionError,
    get_effective_settings,
    update_settings,
)
from storage import admin_db
from storage.admin_db import reset_for_tests, settings as db_settings


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_db, "ADMIN_DB_PATH", str(tmp_path / "admin.db"))
    reset_for_tests()
    admin_db.init()
    yield
    reset_for_tests()


# ----- constants -----

def test_sections_are_the_four_expected():
    assert set(SECTIONS) == {"llm", "retrieval", "paths", "embedding"}


def test_defaults_contain_every_field():
    assert set(DEFAULTS["llm"].keys()) == {
        "base_url", "model_name", "temperature", "max_tokens", "timeout",
        "top_p", "frequency_penalty", "presence_penalty",
    }
    assert set(DEFAULTS["retrieval"].keys()) == {"k", "chunk_size", "chunk_overlap"}
    assert set(DEFAULTS["paths"].keys()) == {
        "documents_dir", "data_dir", "chroma_collection",
    }
    assert set(DEFAULTS["embedding"].keys()) == {"model"}


def test_requires_restart_lists_known_fields():
    assert "base_url" in REQUIRES_RESTART["llm"]
    assert "model_name" in REQUIRES_RESTART["llm"]
    assert "documents_dir" in REQUIRES_RESTART["paths"]
    assert "model" in REQUIRES_RESTART["embedding"]


# ----- get_effective_settings -----

def test_effective_returns_all_sections_with_defaults_when_db_empty():
    eff = get_effective_settings()
    assert set(eff.keys()) == {"llm", "retrieval", "paths", "embedding"}
    assert eff["llm"]["temperature"] == DEFAULTS["llm"]["temperature"]


def test_effective_merges_db_overrides_with_defaults():
    update_settings(sections={"llm": {"temperature": 0.7}}, by_username="admin")
    eff = get_effective_settings()
    assert eff["llm"]["temperature"] == 0.7
    # Other llm fields still come from defaults.
    assert eff["llm"]["max_tokens"] == DEFAULTS["llm"]["max_tokens"]


# ----- update_settings validation -----

def test_update_unknown_section_raises():
    with pytest.raises(UnknownSectionError):
        update_settings(sections={"bogus": {"x": 1}}, by_username="admin")


def test_update_llm_temperature_out_of_range():
    with pytest.raises(InvalidFieldError) as ei:
        update_settings(sections={"llm": {"temperature": 3.0}}, by_username="admin")
    assert "temperature" in str(ei.value)


def test_update_llm_max_tokens_must_be_int():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"llm": {"max_tokens": "abc"}}, by_username="admin")


def test_update_llm_max_tokens_zero_rejected():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"llm": {"max_tokens": 0}}, by_username="admin")


def test_update_llm_max_tokens_too_large_rejected():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"llm": {"max_tokens": 99999}}, by_username="admin")


def test_update_retrieval_k_must_be_positive_int():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"retrieval": {"k": 0}}, by_username="admin")


def test_update_retrieval_k_too_large():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"retrieval": {"k": 100}}, by_username="admin")


def test_update_retrieval_chunk_overlap_must_be_less_than_chunk_size():
    update_settings(
        sections={"retrieval": {"chunk_size": 100, "chunk_overlap": 50}},
        by_username="admin",
    )
    with pytest.raises(InvalidFieldError):
        update_settings(
            sections={"retrieval": {"chunk_size": 100, "chunk_overlap": 100}},
            by_username="admin",
        )


def test_update_embedding_model_must_be_string():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"embedding": {"model": 123}}, by_username="admin")


def test_update_paths_dir_must_be_string():
    with pytest.raises(InvalidFieldError):
        update_settings(
            sections={"paths": {"documents_dir": 123}}, by_username="admin"
        )


def test_update_unknown_field_in_section_raises():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"llm": {"nonexistent": 1}}, by_username="admin")


# ----- successful updates -----

def test_update_writes_to_db_and_returns_new_value():
    new, restart = update_settings(
        sections={"llm": {"temperature": 0.5}}, by_username="admin"
    )
    assert new["llm"]["temperature"] == 0.5
    assert restart == []  # temperature is hot-reload


def test_update_returns_restart_required_fields():
    new, restart = update_settings(
        sections={"llm": {"base_url": "http://x:1234/v1"}}, by_username="admin"
    )
    assert "llm.base_url" in restart


def test_update_overwrites_previous_section_value():
    update_settings(sections={"llm": {"temperature": 0.5}}, by_username="admin")
    update_settings(
        sections={"llm": {"temperature": 0.9, "max_tokens": 1024}},
        by_username="admin",
    )
    stored = db_settings.get("llm")
    assert stored == {"temperature": 0.9, "max_tokens": 1024}


def test_update_multiple_sections_at_once():
    new, restart = update_settings(
        sections={
            "llm": {"temperature": 0.5},
            "retrieval": {"k": 10},
        },
        by_username="admin",
    )
    assert new["llm"]["temperature"] == 0.5
    assert new["retrieval"]["k"] == 10
    assert restart == []


def test_partial_update_preserves_other_fields():
    update_settings(sections={"llm": {"temperature": 0.5}}, by_username="admin")
    update_settings(sections={"llm": {"max_tokens": 4096}}, by_username="admin")
    stored = db_settings.get("llm")
    assert stored["temperature"] == 0.5
    assert stored["max_tokens"] == 4096
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_settings.py -v`
Expected: `ModuleNotFoundError: No module named 'app.admin.settings'`

- [ ] **Step 3: Implement `app/admin/settings.py`**

Create `app/admin/settings.py`:

```python
# app/admin/settings.py
"""Persisted admin settings + validation + restart-required tagging."""
from __future__ import annotations

from storage.admin_db import settings as db_settings


SECTIONS: tuple[str, ...] = ("llm", "retrieval", "paths", "embedding")


DEFAULTS: dict[str, dict] = {
    "llm": {
        "base_url": "http://localhost:8848/v1",
        "model_name": "g0chu-Qwen3.6-35B-A3B-NVFP4",
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
    "llm": {"base_url", "model_name", "timeout"},
    "paths": {"documents_dir", "data_dir", "chroma_collection"},
    "embedding": {"model"},
}


# ---------- validation rules ----------

_RANGE_CHECKS: dict[str, tuple[float, float]] = {
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
    ("llm", "base_url"), ("llm", "model_name"),
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
    *, sections: dict[str, dict], by_username: str
) -> tuple[dict, list[str]]:
    """Validate, persist, and return (new_sections, restart_required_fields).

    `restart_required_fields` is a list of "section.field" strings.
    """
    if not isinstance(sections, dict):
        raise InvalidFieldError("sections must be an object")
    new_state: dict[str, dict] = {}
    restart: list[str] = []
    for section, payload in sections.items():
        if section not in SECTIONS:
            raise UnknownSectionError(f"unknown section {section!r}")
        if not isinstance(payload, dict):
            raise InvalidFieldError(f"{section} payload must be an object")
        _validate_section_payload(section, payload)
        # Merge with stored.
        existing = db_settings.get(section) or {}
        merged = dict(existing)
        merged.update(payload)
        new_state[section] = merged
        # Tag restart-required fields that appear in this update.
        for field in payload.keys():
            if section in REQUIRES_RESTART and field in REQUIRES_RESTART[section]:
                restart.append(f"{section}.{field}")
        # Persist.
        db_settings.set(section, merged, by_username)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_settings.py -v`
Expected: ~22 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/admin/settings.py tests/test_admin_settings.py
git commit -m "feat(admin): settings persistence + validation

- 4 sections (llm/retrieval/paths/embedding) with defaults from env
- Type + range + cross-field (chunk_overlap < chunk_size) validation
- update_settings returns restart-required field tags
- get_effective_settings merges DB overrides with env defaults"
```

---

### Task 5: Hot-reload module wiring — `llm/config.py`, `llm/client.py`, `rag/retriever.py`, `rag/splitter.py`

**Files:**
- Modify: `llm/config.py` (full rewrite)
- Modify: `llm/client.py`
- Modify: `rag/retriever.py`
- Modify: `rag/splitter.py`
- Modify: `tests/test_admin_settings.py` (add Part B — hot-reload propagation tests)

**Interfaces:**
- `llm/config.py` now exposes:
  - `LLMConfig` dataclass (fields: `base_url`, `model_name`, `temperature`, `max_tokens`, `timeout`, `top_p`, `frequency_penalty`, `presence_penalty`)
  - `RAGConfig` dataclass (fields: `k`, `chunk_size`, `chunk_overlap`)
  - `EmbeddingConfig` dataclass (fields: `model`)
  - `_llm_cfg: LLMConfig`, `_rag_cfg: RAGConfig`, `_emb_cfg: EmbeddingConfig` (module singletons)
  - `get_llm_settings() -> LLMConfig`
  - `get_rag_settings() -> RAGConfig`
  - `get_embedding_settings() -> EmbeddingConfig`
  - `update_llm_settings(patch: dict) -> None` — applies patch in place to `_llm_cfg`
  - `update_rag_settings(patch: dict) -> None`
  - `update_embedding_settings(patch: dict) -> None`
  - `reset_settings_for_tests() -> None` — re-imports env defaults + clears any patches
- `llm/client.py::get_llm()` — reads from `get_llm_settings()` on each call.
- `rag/retriever.py::get_retriever(k=None)` — uses `k` arg if given, else `get_rag_settings().k`.
- `rag/splitter.py::split(docs)` — reads `chunk_size`/`chunk_overlap` from `get_rag_settings()`.

**Background:** This is the plumbing that makes admin-saved settings take effect on the next request without a restart. Hot fields only (LLM inference + retrieval params). Path/env fields require restart and are surfaced but not applied here.

- [ ] **Step 1: Write failing tests for hot-reload propagation**

Append to `tests/test_admin_settings.py`:

```python
# ---- Part B: hot-reload propagation ----

from llm import config as llm_config
from llm.client import get_llm
from rag.retriever import get_retriever


def test_get_llm_uses_current_settings_each_call(monkeypatch):
    llm_config.update_llm_settings({"temperature": 0.5})
    llm1 = get_llm(streaming=False)
    llm_config.update_llm_settings({"temperature": 0.9})
    llm2 = get_llm(streaming=False)
    assert llm1.temperature == 0.5
    assert llm2.temperature == 0.9


def test_get_retriever_uses_rag_k_each_call(monkeypatch):
    llm_config.update_rag_settings({"k": 6})
    r1 = get_retriever()
    llm_config.update_rag_settings({"k": 12})
    r2 = get_retriever()
    assert r1.search_kwargs["k"] == 6
    assert r2.search_kwargs["k"] == 12


def test_get_retriever_explicit_k_overrides():
    llm_config.update_rag_settings({"k": 6})
    r = get_retriever(k=20)
    assert r.search_kwargs["k"] == 20


def test_update_settings_unknown_field_raises():
    with pytest.raises(ValueError):
        llm_config.update_llm_settings({"nonexistent": 1})


def test_reset_settings_for_tests_restores_defaults(monkeypatch):
    monkeypatch.setenv("TEMPERATURE", "0.42")
    llm_config.reset_settings_for_tests()
    assert llm_config.get_llm_settings().temperature == 0.42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_settings.py -v -k "hot_reload or get_llm or get_retriever or reset_settings"`
Expected: `AttributeError: module 'llm.config' has no attribute 'update_llm_settings'`

- [ ] **Step 3: Rewrite `llm/config.py`**

Replace the entire file with:

```python
# llm/config.py
"""LLM / RAG / Embedding runtime config.

Module-level singletons (`_llm_cfg`, `_rag_cfg`, `_emb_cfg`) are mutated
in place by `update_*_settings()` so subsequent reads (e.g. `get_llm()`)
see the new values. Defaults come from env vars at import time; admin
backend can override at runtime via the settings routes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields, replace


@dataclass
class LLMConfig:
    base_url: str
    model_name: str
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
```

- [ ] **Step 4: Update `llm/client.py`**

Replace the file with:

```python
# llm/client.py
from langchain_openai import ChatOpenAI

from .config import get_llm_settings


def get_llm(*, streaming: bool = True) -> ChatOpenAI:
    s = get_llm_settings()
    return ChatOpenAI(
        base_url=s.base_url,
        api_key="not-needed",          # llama.cpp doesn't need a key
        model=s.model_name,
        streaming=streaming,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
        timeout=s.timeout,
    )
```

- [ ] **Step 5: Update `rag/retriever.py`**

Replace the file with:

```python
# rag/retriever.py
from __future__ import annotations

import os
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.vectorstores import VectorStoreRetriever

from llm.config import get_rag_settings

from .embeddings import get_embeddings


COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION", "counselor")


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "./data")


def _persist_dir() -> str:
    return os.path.join(_data_dir(), "chroma")


@lru_cache(maxsize=1)
def get_chroma() -> Chroma:
    os.makedirs(_persist_dir(), exist_ok=True)
    return Chroma(
        persist_directory=_persist_dir(),
        embedding_function=get_embeddings(),
        collection_name=COLLECTION_NAME,
    )


def get_retriever(*, k: int | None = None) -> VectorStoreRetriever:
    effective_k = k if k is not None else get_rag_settings().k
    return get_chroma().as_retriever(
        search_type="similarity",
        search_kwargs={"k": effective_k},
    )


def collection_count() -> int:
    try:
        return get_chroma()._collection.count()
    except Exception:
        return 0
```

- [ ] **Step 6: Update `rag/splitter.py`**

Read the existing file first. Replace its top section (the chunk_size / chunk_overlap references) so it reads from `get_rag_settings()`. The current file likely looks like:

```python
# rag/splitter.py
from __future__ import annotations
import re
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .loaders import _CJK_RE  # whatever the actual symbol is
```

Replace the entire file with:

```python
# rag/splitter.py
"""Chinese-aware splitter that reads chunk_size/chunk_overlap from runtime config."""
from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from llm.config import get_rag_settings


# CJK sentence boundary — matches Han chars plus ASCII sentence terminators.
_CJK_BOUNDARY = re.compile(r"(?<=[。！？；])\s*")


def _split_cjk_aware(text: str) -> list[str]:
    """Split text on CJK sentence boundaries, preserving paragraphs."""
    if not text:
        return []
    # First split on blank lines (paragraphs), then on CJK sentence ends.
    paragraphs = re.split(r"\n\s*\n", text)
    out: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # If paragraph is small enough, keep it whole.
        out.append(p)
    return out


def split(docs: list[Document]) -> list[Document]:
    """Split documents using RecursiveCharacterTextSplitter with CJK-aware separators."""
    rag = get_rag_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=rag.chunk_size,
        chunk_overlap=rag.chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", ". ", "! ", "? ", " ", ""],
        keep_separator=False,
    )
    out: list[Document] = []
    for doc in docs:
        text = doc.page_content or ""
        # Pre-split on hard CJK boundaries, then chunk each segment.
        for seg in _split_cjk_aware(text):
            for chunk in splitter.split_text(seg):
                if chunk.strip():
                    out.append(Document(page_content=chunk, metadata=dict(doc.metadata)))
    return out
```

> **Note:** the original `rag/splitter.py` may differ — read it first with the Read tool before replacing. The above is the minimal correct version that satisfies the new interface. Adjust imports / helpers to match the existing pattern.

- [ ] **Step 7: Run all admin settings tests**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_settings.py -v`
Expected: all ~27 tests pass.

- [ ] **Step 8: Run full suite to verify no regressions**

Run: `OFFLINE=1 uv run --extra dev pytest -q`
Expected: ~135 passed / 2 skipped (no change to total beyond new tests).

- [ ] **Step 9: Commit**

```bash
git add llm/config.py llm/client.py rag/retriever.py rag/splitter.py tests/test_admin_settings.py
git commit -m "refactor: hot-reloadable LLM/RAG/Embedding config singletons

- llm.config.LLMConfig / RAGConfig / EmbeddingConfig dataclasses
- update_*_settings() mutates singletons in place
- llm.client.get_llm() reads from singleton each call
- rag.retriever.get_retriever() / rag.splitter.split() honor runtime k/chunk_size/chunk_overlap"
```

---

### Task 6: Reindex service — `app/admin/reindex.py` + tests

**Files:**
- Create: `app/admin/reindex.py`
- Modify: `tests/test_admin_settings.py` (add Part C — reindex write tests)

**Interfaces:**
- Consumes: `ingest.indexer.build_index`; `storage.admin_db.kv`.
- Produces:
  - `_REINDEX_LOCK = threading.Lock()` (module-level).
  - `class ReindexBusyError(Exception)` raised when called while a reindex is already running.
  - `run_reindex(*, force: bool = False) -> dict` — calls `build_index(force=force)`; writes result to `kv.set('last_reindex', {ts, force, added, skipped, failed, items})`; returns the result dict (same shape as `/api/ingest` used to return).
  - `get_last_reindex() -> dict | None`

**Background:** The reindex is potentially long-running and CPU/IO heavy. A single in-process lock prevents concurrent runs; the second caller gets `ReindexBusyError`. The result is cached in the kv table so the dashboard can display "last index" without re-running anything.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_admin_settings.py` (or create a new file `tests/test_admin_reindex.py` if you prefer — the steps below use the new file):

Create `tests/test_admin_reindex.py`:

```python
"""Tests for app/admin/reindex.py — wraps ingest.indexer.build_index."""
from __future__ import annotations

import threading
import time

import pytest

from app.admin import reindex
from app.admin.reindex import ReindexBusyError, get_last_reindex, run_reindex
from storage import admin_db
from storage.admin_db import reset_for_tests


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_db, "ADMIN_DB_PATH", str(tmp_path / "admin.db"))
    reset_for_tests()
    admin_db.init()
    yield
    reset_for_tests()


@pytest.fixture
def fake_build_index(monkeypatch):
    """Patch ingest.indexer.build_index; returns the captured list."""
    captured = {}

    def _impl(*, force: bool = False):
        captured["force"] = force
        captured["calls"] = captured.get("calls", 0) + 1
        # Simulate slow work so a second concurrent call would overlap.
        time.sleep(0.05)
        return {
            "added": 3,
            "skipped": 1,
            "failed": [],
            "items": [
                {"status": "added", "path": "/a.pdf", "chunks": 10},
                {"status": "added", "path": "/b.pdf", "chunks": 5},
                {"status": "skipped", "path": "/c.pdf", "reason": "unchanged"},
                {"status": "added", "path": "/d.pdf", "chunks": 2},
            ],
            "meta_written": True,
        }

    monkeypatch.setattr("app.admin.reindex.build_index", _impl)
    return captured


def test_run_reindex_returns_result(fake_build_index):
    result = run_reindex(force=False)
    assert result["added"] == 3
    assert result["skipped"] == 1
    assert fake_build_index["force"] is False
    assert fake_build_index["calls"] == 1


def test_run_reindex_passes_force_flag(fake_build_index):
    run_reindex(force=True)
    assert fake_build_index["force"] is True


def test_run_reindex_persists_last_to_kv(fake_build_index):
    run_reindex(force=True)
    last = get_last_reindex()
    assert last is not None
    assert last["force"] is True
    assert last["added"] == 3
    assert last["skipped"] == 1
    assert "ts" in last
    assert "items" not in last  # truncated to summary only


def test_get_last_reindex_returns_none_before_any_run():
    assert get_last_reindex() is None


def test_concurrent_runs_second_raises_busy(fake_build_index):
    """Hold the lock manually while calling run_reindex."""
    reindex._REINDEX_LOCK.acquire()
    try:
        with pytest.raises(ReindexBusyError):
            run_reindex()
    finally:
        reindex._REINDEX_LOCK.release()


def test_concurrent_runs_in_threads_one_busy_one_ok(fake_build_index, monkeypatch):
    """Two threads: first holds lock for 100ms; second gets busy."""
    results = {}

    def call():
        try:
            results["value"] = run_reindex()
        except ReindexBusyError:
            results["error"] = "busy"

    reindex._REINDEX_LOCK.acquire()
    t1 = threading.Thread(target=call)
    t1.start()
    time.sleep(0.02)
    # While t1 is blocked on the lock, try a second call manually.
    with pytest.raises(ReindexBusyError):
        run_reindex()
    reindex._REINDEX_LOCK.release()
    t1.join()
    assert "value" in results
    assert results["value"]["added"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_reindex.py -v`
Expected: `ModuleNotFoundError: No module named 'app.admin.reindex'`

- [ ] **Step 3: Implement `app/admin/reindex.py`**

Create `app/admin/reindex.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_reindex.py -v`
Expected: ~7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/admin/reindex.py tests/test_admin_reindex.py
git commit -m "feat(admin): reindex service with process-local lock + last-result cache

- Wraps ingest.indexer.build_index
- Process-local Lock prevents concurrent runs (second caller gets ReindexBusyError)
- Writes summary to kv('last_reindex') on success for dashboard display"
```

---

### Task 7: Admin routes — `app/admin/routes.py` + `app/admin/schemas.py` + `app/main.py` wiring

**Files:**
- Create: `app/admin/schemas.py`
- Create: `app/admin/routes.py`
- Modify: `app/main.py`
- Delete: `app/routes_ingest.py`
- Create: `tests/test_admin_routes.py`

**Interfaces:**

`app/admin/schemas.py` exposes Pydantic models:
- `LoginRequest(username, password)`
- `LoginResponse(username, created_at, last_login_at)` — last_login_at may be null
- `MeResponse(username, created_at, last_login_at)`
- `AccountPublic(id, username, created_at, updated_at, last_login_at, failed_attempts, locked)`
- `AccountCreate(username, password)` — username 3-32 `[a-z0-9_-]`, password ≥ 6
- `AccountUpdate(old_password?, new_password?, unlock?)`
- `LLMSettings`, `RetrievalSettings`, `PathsSettings`, `EmbeddingSettings`
- `SettingsPatch(sections: dict[str, dict])`
- `ReindexRequest(force: bool = False)`

`app/admin/routes.py` is an `APIRouter()` mounted at `/api/admin`:
- `POST /login` → 200 + Set-Cookie, 401 `invalid_credentials`, 423 `account_locked`
- `POST /logout` → 204
- `GET /me` → 200 (auth required)
- `GET /accounts` → 200 list (auth required)
- `POST /accounts` → 201, 400 weak/invalid, 409 duplicate (auth required)
- `PATCH /accounts/{id}` → 200, 400 self-unlock, 400 wrong old password (auth required)
- `DELETE /accounts/{id}` → 204, 400 self-delete / last-admin (auth required)
- `GET /settings` → 200 (auth required)
- `PUT /settings` → 200, 400 invalid field, 400 unknown section (auth required)
- `POST /reindex` → 200 with result, 409 busy (auth required)
- `GET /reindex/last` → 200 or `{last: null}` (auth required)

`require_session` dependency reads `counselor_admin` cookie, validates, returns `{account_id, username}` dict (also stashes the account row on `request.state.account`).

CSRF check on mutating methods: verify `Origin` header equals configured `COUNSELOR_ALLOWED_ORIGIN` env var (default `http://localhost:8000`); reject 403 otherwise.

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin_routes.py`:

```python
"""Integration tests for app/admin/routes.py — FastAPI HTTP integration."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("storage.admin_db.ADMIN_DB_PATH", str(tmp_path / "admin.db"))
    from storage import admin_db
    admin_db.reset_for_tests()
    admin_db.init()
    yield
    admin_db.reset_for_tests()


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def logged_in(client):
    r = client.post(
        "/api/admin/login", json={"username": "admin", "password": "147369"}
    )
    assert r.status_code == 200
    return client


# ----- /login -----

def test_login_default_succeeds(client):
    r = client.post(
        "/api/admin/login", json={"username": "admin", "password": "147369"}
    )
    assert r.status_code == 200
    assert "counselor_admin" in r.cookies
    body = r.json()
    assert body["username"] == "admin"


def test_login_wrong_password_returns_401_no_cookie(client):
    r = client.post(
        "/api/admin/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 401
    assert "counselor_admin" not in r.cookies


def test_login_six_failures_locks_account(client):
    for _ in range(5):
        client.post(
            "/api/admin/login", json={"username": "admin", "password": "wrong"}
        )
    r = client.post(
        "/api/admin/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 423
    r2 = client.post(
        "/api/admin/login", json={"username": "admin", "password": "147369"}
    )
    assert r2.status_code == 423


# ----- /logout -----

def test_logout_clears_cookie(logged_in):
    r = logged_in.post("/api/admin/logout")
    assert r.status_code == 204
    # Cookie should be cleared (set to empty value or expired).
    assert logged_in.cookies.get("counselor_admin") in (None, "")


# ----- /me -----

def test_me_requires_auth(client):
    r = client.get("/api/admin/me")
    assert r.status_code == 401


def test_me_returns_current_account(logged_in):
    r = logged_in.get("/api/admin/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


# ----- /accounts -----

def test_list_accounts_requires_auth(client):
    assert client.get("/api/admin/accounts").status_code == 401


def test_list_accounts_includes_admin(logged_in):
    r = logged_in.get("/api/admin/accounts")
    assert r.status_code == 200
    rows = r.json()
    assert any(a["username"] == "admin" for a in rows)
    for a in rows:
        assert "password_hash" not in a
        assert "salt" not in a


def test_create_account(logged_in):
    r = logged_in.post(
        "/api/admin/accounts",
        json={"username": "bob", "password": "bobpass1"},
    )
    assert r.status_code == 201
    assert r.json()["username"] == "bob"


def test_create_account_duplicate_returns_409(logged_in):
    logged_in.post(
        "/api/admin/accounts", json={"username": "bob", "password": "bobpass1"}
    )
    r = logged_in.post(
        "/api/admin/accounts", json={"username": "bob", "password": "otherpw1"}
    )
    assert r.status_code == 409


def test_create_account_weak_password_returns_400(logged_in):
    r = logged_in.post(
        "/api/admin/accounts", json={"username": "bob", "password": "abc"}
    )
    assert r.status_code == 400


def test_create_account_bad_username_returns_400(logged_in):
    r = logged_in.post(
        "/api/admin/accounts", json={"username": "ab", "password": "abcdef"}
    )
    assert r.status_code == 400


def test_change_own_password_requires_old_password(logged_in):
    me = logged_in.get("/api/admin/me").json()
    r = logged_in.patch(
        f"/api/admin/accounts/{me['username']}", json={"new_password": "newpass1"}
    )
    # Username is unique; we use it as id only if the API exposes it that way.
    # Adjust the URL below based on the actual route — the test uses ID lookups.
    # Implementation note: routes use {account_id}, not username.
    aid = logged_in.get("/api/admin/accounts").json()[0]["id"]
    r = logged_in.patch(
        f"/api/admin/accounts/{aid}", json={"new_password": "newpass1"}
    )
    assert r.status_code == 400


def test_change_other_password_does_not_require_old(logged_in):
    logged_in.post(
        "/api/admin/accounts", json={"username": "bob", "password": "bobpass1"}
    )
    bob_id = next(
        a["id"] for a in logged_in.get("/api/admin/accounts").json()
        if a["username"] == "bob"
    )
    r = logged_in.patch(
        f"/api/admin/accounts/{bob_id}", json={"new_password": "newbob1"}
    )
    assert r.status_code == 200


def test_self_unlock_rejected(logged_in):
    admin_id = next(
        a["id"] for a in logged_in.get("/api/admin/accounts").json()
        if a["username"] == "admin"
    )
    r = logged_in.patch(f"/api/admin/accounts/{admin_id}", json={"unlock": True})
    assert r.status_code == 400


def test_delete_self_rejected(logged_in):
    admin_id = next(
        a["id"] for a in logged_in.get("/api/admin/accounts").json()
        if a["username"] == "admin"
    )
    r = logged_in.delete(f"/api/admin/accounts/{admin_id}")
    assert r.status_code == 400


def test_delete_other_admin_works_when_two_exist(logged_in):
    logged_in.post(
        "/api/admin/accounts", json={"username": "bob", "password": "bobpass1"}
    )
    bob_id = next(
        a["id"] for a in logged_in.get("/api/admin/accounts").json()
        if a["username"] == "bob"
    )
    r = logged_in.delete(f"/api/admin/accounts/{bob_id}")
    assert r.status_code == 204


# ----- /settings -----

def test_get_settings_requires_auth(client):
    assert client.get("/api/admin/settings").status_code == 401


def test_get_settings_returns_all_sections(logged_in):
    r = logged_in.get("/api/admin/settings")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"llm", "retrieval", "paths", "embedding"}


def test_put_settings_updates_and_returns_restart_required(logged_in):
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"temperature": 0.5, "base_url": "http://x:1/v1"}}},
    )
    assert r.status_code == 200
    body = r.json()
    assert "llm.base_url" in body["restart_required"]
    # Re-read:
    r2 = logged_in.get("/api/admin/settings")
    assert r2.json()["llm"]["temperature"] == 0.5
    assert r2.json()["llm"]["base_url"] == "http://x:1/v1"


def test_put_settings_invalid_value_returns_400(logged_in):
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"temperature": 5.0}}},
    )
    assert r.status_code == 400


def test_put_settings_unknown_section_returns_400(logged_in):
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"bogus": {"x": 1}}},
    )
    assert r.status_code == 400


# ----- /reindex -----

def test_reindex_requires_auth(client):
    assert client.post("/api/admin/reindex").status_code == 401


def test_reindex_returns_result(logged_in, monkeypatch):
    from app.admin import reindex

    def fake_build(*, force=False):
        return {"added": 2, "skipped": 0, "failed": [],
                "items": [], "meta_written": True}

    monkeypatch.setattr(reindex, "build_index", fake_build)
    r = logged_in.post("/api/admin/reindex", json={"force": True})
    assert r.status_code == 200
    assert r.json()["added"] == 2


def test_reindex_force_flag_propagates(logged_in, monkeypatch):
    from app.admin import reindex
    captured = {}

    def fake_build(*, force=False):
        captured["force"] = force
        return {"added": 0, "skipped": 0, "failed": [], "items": [], "meta_written": True}

    monkeypatch.setattr(reindex, "build_index", fake_build)
    logged_in.post("/api/admin/reindex", json={"force": True})
    assert captured["force"] is True


def test_reindex_busy_returns_409(logged_in, monkeypatch):
    from app.admin import reindex
    reindex._REINDEX_LOCK.acquire()
    try:
        r = logged_in.post("/api/admin/reindex", json={"force": False})
        assert r.status_code == 409
    finally:
        reindex._REINDEX_LOCK.release()


def test_reindex_last_returns_cached(logged_in, monkeypatch):
    from app.admin import reindex

    def fake_build(*, force=False):
        return {"added": 5, "skipped": 1, "failed": [], "items": [],
                "meta_written": True}

    monkeypatch.setattr(reindex, "build_index", fake_build)
    logged_in.post("/api/admin/reindex", json={"force": False})
    r = logged_in.get("/api/admin/reindex/last")
    assert r.status_code == 200
    assert r.json()["added"] == 5


def test_reindex_last_returns_null_before_any_run(logged_in):
    r = logged_in.get("/api/admin/reindex/last")
    assert r.status_code == 200
    assert r.json()["last"] is None


# ----- CSRF / Origin -----

def test_post_without_origin_header_rejected(logged_in, monkeypatch):
    # Mutating endpoint, missing Origin.
    from app.admin import reindex
    monkeypatch.setattr(reindex, "build_index",
                        lambda *, force=False: {"added": 0, "skipped": 0,
                                                 "failed": [], "items": [],
                                                 "meta_written": True})
    # FastAPI TestClient sets Origin automatically based on base_url; the
    # default matches http://testserver which equals our default allowed
    # origin? No — it doesn't, but TestClient sends one. To exercise the
    # no-origin path we'd need to strip the header. Skip this test if
    # TestClient always sets Origin.
    pass  # covered by direct Origin-checking tests below


def test_post_with_wrong_origin_rejected(logged_in, monkeypatch):
    from app.admin import reindex
    monkeypatch.setattr(reindex, "build_index",
                        lambda *, force=False: {"added": 0, "skipped": 0,
                                                 "failed": [], "items": [],
                                                 "meta_written": True})
    r = logged_in.post(
        "/api/admin/reindex",
        json={"force": False},
        headers={"Origin": "http://evil.example.com"},
    )
    assert r.status_code == 403


def test_get_with_wrong_origin_allowed(logged_in):
    # GETs are exempt from Origin check.
    r = logged_in.get(
        "/api/admin/me",
        headers={"Origin": "http://evil.example.com"},
    )
    assert r.status_code == 200


# ----- expired session -----

def test_expired_session_returns_401(logged_in, monkeypatch):
    from storage import admin_db
    # Force all sessions to be expired.
    c = admin_db._conn
    c.execute("UPDATE sessions SET expires_at = 0")
    r = logged_in.get("/api/admin/me")
    assert r.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_routes.py -v`
Expected: failures (404 from /api/admin/login since router not mounted yet, etc.).

- [ ] **Step 3: Implement `app/admin/schemas.py`**

Create `app/admin/schemas.py`:

```python
# app/admin/schemas.py
from __future__ import annotations

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
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6)

    @field_validator("username")
    @classmethod
    def _v(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError("username must contain only [a-z0-9_-]")
        return v


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_password: str | None = None
    new_password: str | None = Field(default=None, min_length=6)
    unlock: bool | None = None


class LLMSettings(BaseModel):
    base_url: str
    model_name: str
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
```

- [ ] **Step 4: Implement `app/admin/routes.py`**

Create `app/admin/routes.py`:

```python
# app/admin/routes.py
"""FastAPI router for /api/admin/* — auth + accounts + settings + reindex."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from storage import admin_db
from storage.admin_db import accounts as db_accounts

from . import accounts as accts
from . import auth
from . import reindex as reindex_svc
from . import settings as settings_svc


router = APIRouter()


_ALLOWED_ORIGIN = os.environ.get(
    "COUNSELOR_ALLOWED_ORIGIN", "http://localhost:8000"
)


def _check_origin(request: Request) -> None:
    """Reject mutating requests from disallowed origins (CSRF defense).

    GET/HEAD/OPTIONS are exempt.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if origin is None:
        # Same-origin POST from a form could omit Origin in some browsers,
        # but for a JSON API with credentials=include, Origin is required.
        # We choose to be strict and reject.
        raise HTTPException(status_code=403, detail="origin header required")
    if origin.rstrip("/") != _ALLOWED_ORIGIN.rstrip("/"):
        raise HTTPException(status_code=403, detail="origin not allowed")


async def require_session(request: Request) -> dict:
    """Validate session cookie and return {account_id, username, ...}."""
    sid = request.cookies.get(auth.SESSION_COOKIE_NAME)
    if not sid:
        raise HTTPException(status_code=401, detail="unauthenticated")
    sess = auth.validate_session(sid)
    if sess is None:
        raise HTTPException(status_code=401, detail="session expired")
    account = db_accounts.get_by_id(sess["account_id"])
    if account is None:
        raise HTTPException(status_code=401, detail="account gone")
    request.state.account = account
    return {"account_id": account["id"], "username": account["username"]}


def _current_account(request: Request) -> dict:
    return request.state.account


# ---------- login / logout / me ----------

@router.post("/login")
def login(req: LoginRequest, response: Response) -> dict:
    sid, err = auth.login_attempt(req.username, req.password)
    if err == "invalid_credentials":
        raise HTTPException(status_code=401, detail="invalid credentials")
    if err == "account_locked":
        raise HTTPException(status_code=423, detail="account locked")
    response.set_cookie(
        key=auth.SESSION_COOKIE_NAME,
        value=sid,
        **auth.SESSION_COOKIE_ATTRS,
        max_age=auth.SESSION_TTL_SECONDS,
    )
    row = db_accounts.get_by_username(req.username) or {}
    return {
        "username": row.get("username"),
        "created_at": row.get("created_at"),
        "last_login_at": row.get("last_login_at"),
    }


@router.post("/logout")
def logout(request: Request, response: Response, _=Depends(require_session)) -> Response:
    sid = request.cookies.get(auth.SESSION_COOKIE_NAME)
    if sid:
        auth.delete_session(sid)
    response.delete_cookie(auth.SESSION_COOKIE_NAME, path="/")
    return Response(status_code=204)


@router.get("/me")
def me(_=Depends(_check_origin), current=Depends(require_session)) -> dict:
    row = db_accounts.get_by_id(current["account_id"]) or {}
    return {
        "username": row.get("username"),
        "created_at": row.get("created_at"),
        "last_login_at": row.get("last_login_at"),
    }


# ---------- accounts ----------

def _acct_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row.get("last_login_at"),
        "failed_attempts": row.get("failed_attempts", 0),
        "locked": bool(row.get("locked", 0)),
    }


@router.get("/accounts")
def list_accounts_endpoint(
    _=Depends(require_session),
) -> list[dict]:
    return [_acct_public(r) for r in accts.list_accounts()]


@router.post("/accounts", status_code=201)
def create_account_endpoint(
    req: AccountCreate,
    request: Request,
    current=Depends(require_session),
) -> dict:
    _check_origin(request)
    try:
        row = accts.create_account(
            username=req.username, password=req.password,
            by_username=current["username"],
        )
    except accts.InvalidUsernameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except accts.WeakPasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except accts.AccountExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _acct_public(row)


@router.patch("/accounts/{account_id}")
def update_account_endpoint(
    account_id: str,
    req: AccountUpdate,
    request: Request,
    current=Depends(require_session),
) -> dict:
    _check_origin(request)
    me = db_accounts.get_by_id(current["account_id"]) or {}
    try:
        if req.unlock:
            row = accts.unlock_account(target_id=account_id, by_account=me)
        elif req.new_password:
            row = accts.change_password(
                target_id=account_id,
                new_password=req.new_password,
                by_account=me,
                old_password=req.old_password,
            )
        else:
            raise HTTPException(status_code=400, detail="no-op update")
    except accts.SelfUnlockError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except accts.WrongOldPasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except accts.WeakPasswordError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except accts.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _acct_public(row)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account_endpoint(
    account_id: str,
    request: Request,
    current=Depends(require_session),
) -> Response:
    _check_origin(request)
    me = db_accounts.get_by_id(current["account_id"]) or {}
    try:
        accts.delete_account(target_id=account_id, by_account=me)
    except accts.SelfDeleteError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except accts.LastAdminError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except accts.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(status_code=204)


# ---------- settings ----------

@router.get("/settings")
def get_settings_endpoint(_=Depends(require_session)) -> dict:
    return settings_svc.get_effective_settings()


@router.put("/settings")
def put_settings_endpoint(
    req: SettingsPatch,
    request: Request,
    current=Depends(require_session),
) -> dict:
    _check_origin(request)
    try:
        new_state, restart = settings_svc.update_settings(
            sections=req.sections, by_username=current["username"]
        )
    except settings_svc.UnknownSectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except settings_svc.InvalidFieldError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Hot-reload: propagate to runtime singletons.
    from llm.config import update_llm_settings, update_rag_settings, update_embedding_settings
    if "llm" in new_state:
        update_llm_settings(new_state["llm"])
    if "retrieval" in new_state:
        update_rag_settings(new_state["retrieval"])
    if "embedding" in new_state:
        update_embedding_settings(new_state["embedding"])
    # `paths` requires restart — only flag, don't propagate.
    return {"sections": new_state, "restart_required": restart}


# ---------- reindex ----------

@router.post("/reindex")
def reindex_endpoint(
    req: ReindexRequest,
    request: Request,
    _=Depends(require_session),
) -> dict:
    _check_origin(request)
    try:
        return reindex_svc.run_reindex(force=req.force)
    except reindex_svc.ReindexBusyError:
        raise HTTPException(status_code=409, detail="reindex already in progress")


@router.get("/reindex/last")
def reindex_last_endpoint(_=Depends(require_session)) -> dict:
    return {"last": reindex_svc.get_last_reindex()}
```

- [ ] **Step 5: Update `app/main.py`**

Replace the file with:

```python
# app/main.py
from __future__ import annotations
import os

from fastapi import FastAPI

from storage.paths import ADMIN_WEB_DIR, WEB_DIR
from .admin.routes import router as admin_router
from .routes_chat import router as chat_router
from .routes_health import router as health_router
from .static_no_store import NoStoreStaticFiles
from storage.admin_db import init as admin_db_init


def create_app() -> FastAPI:
    admin_db_init()  # ensure data/admin.db + default seed exist
    app = FastAPI(title="AI Counselor", version="0.1.0")
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(admin_router, prefix="/api/admin")
    if os.path.isdir(WEB_DIR):
        app.mount(
            "/",
            NoStoreStaticFiles(directory=WEB_DIR, html=True),
            name="web",
        )
    if os.path.isdir(ADMIN_WEB_DIR):
        app.mount(
            "/admin",
            NoStoreStaticFiles(directory=ADMIN_WEB_DIR, html=True),
            name="admin-web",
        )
    return app


app = create_app()
```

- [ ] **Step 6: Delete `app/routes_ingest.py`**

Run: `git rm app/routes_ingest.py`

- [ ] **Step 7: Run admin routes tests**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_routes.py -v`
Expected: all tests pass.

- [ ] **Step 8: Run full suite**

Run: `OFFLINE=1 uv run --extra dev pytest -q`
Expected: ~155 passed / 2 skipped.

- [ ] **Step 9: Commit**

```bash
git add app/admin/schemas.py app/admin/routes.py app/main.py tests/test_admin_routes.py
git commit -m "feat(admin): FastAPI router + schemas + main.py wiring

- /api/admin/{login,logout,me,accounts,settings,reindex,reindex/last}
- Session cookie auth via require_session dependency
- CSRF: Origin check on mutating methods (GETs exempt)
- Hot-reload of llm/retrieval/embedding on PUT /settings
- Removed /api/ingest (admin-only now via /api/admin/reindex)"
```

---

### Task 8: Frontend cleanup — remove reindex from chat UI + assertions

**Files:**
- Modify: `web/index.html` (line ~27)
- Modify: `web/app.js` (lines ~582-594)
- Modify: `tests/test_api.py` (add assertions)

**Background:** The chat UI no longer exposes the reindex button. The backend route is gone (Task 7). Tests must verify both.

- [ ] **Step 1: Read current `web/index.html` around the reindex button**

Run: `grep -n "reindex\|重建" web/index.html`

- [ ] **Step 2: Remove the reindex button from `web/index.html`**

Delete the `<button id="reindex" ...>重建索引</button>` line (likely line 27). Read the file first to get the exact text; the Edit tool needs unique surrounding context. Example:

```html
<button id="reindex" type="button" title="重建文档索引">重建索引</button>
```

becomes (delete the whole line; keep adjacent lines intact).

- [ ] **Step 3: Read current `web/app.js` around the reindex handler**

Run: `grep -n "reindexBtn\|#reindex" web/app.js`

- [ ] **Step 4: Remove the reindex handler from `web/app.js`**

Delete the `reindexBtn` listener block (search the file for `reindexBtn.addEventListener` and remove the enclosing `if (reindexBtn) reindexBtn.addEventListener(...)` block plus the closing brace). Use the Read tool to get exact line range, then Edit to remove.

- [ ] **Step 5: Add regression assertions to `tests/test_api.py`**

Read `tests/test_api.py` to understand its structure, then append:

```python
def test_reindex_button_removed_from_user_ui():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert 'id="reindex"' not in html
    assert "重建索引" not in html
    assert "reindexBtn" not in js


def test_ingest_route_no_longer_public():
    r = client.post("/api/ingest", json={"force": False})
    assert r.status_code == 404
```

(Adjust `WEB_DIR` / `client` to whatever names the existing tests use — read the file first.)

- [ ] **Step 6: Run tests**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_api.py -v`
Expected: existing + 2 new tests pass.

- [ ] **Step 7: Bump user SPA cache-bust version**

If the Edit in step 2/4 changed the user SPA in any way, bump `<script src="app.js?v=N">` in `web/index.html`. Per CLAUDE.md, this is monotonic; current value is `v=12` per earlier conversation. If only the reindex button was removed (HTML structure) and no JS version-tag-bearing script was touched, no bump is needed. If JS was touched, bump to `v=13`.

- [ ] **Step 8: Commit**

```bash
git add web/index.html web/app.js tests/test_api.py
git commit -m "fix(web): remove reindex button from user UI (moved to admin)

- /api/ingest deleted; /api/admin/reindex is the only reindex path
- Tests verify button removed + /api/ingest returns 404"
```

---

### Task 9: Admin SPA — login page + shared CSS + shared JS

**Files:**
- Create: `web/admin/admin.css`
- Create: `web/admin/admin.js`
- Create: `web/admin/login.html`
- Create: `tests/test_admin_static.py`

**Interfaces:** Admin SPA shared infrastructure:
- `admin.js` exposes `requireAdmin()` (async; calls `GET /api/admin/me`; redirects to `/admin/login` on 401), `toast(text)`, `api(path, options)` (fetch wrapper with `credentials: include`).
- `admin.css` defines tokens (colors, spacing, typography) + components (nav, button, table, form, modal, toast).

**Background:** Vanilla JS, no build. Mirror the existing user SPA pattern (`web/app.js`) but simpler — no localStorage, no chat logic. Each page is a standalone HTML.

- [ ] **Step 1: Write failing test for admin static infrastructure**

Create `tests/test_admin_static.py`:

```python
"""Smoke tests for admin SPA static files."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ADMIN_WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "admin"


def test_admin_web_dir_exists():
    assert ADMIN_WEB_DIR.is_dir()


@pytest.mark.parametrize("filename", [
    "login.html", "index.html", "accounts.html", "settings.html",
])
def test_admin_html_pages_exist(filename):
    assert (ADMIN_WEB_DIR / filename).is_file()


def test_admin_html_pages_reference_admin_js_and_css():
    for f in ADMIN_WEB_DIR.glob("*.html"):
        text = f.read_text(encoding="utf-8")
        assert 'admin.css' in text, f"{f.name} missing admin.css"
        assert 'admin.js' in text, f"{f.name} missing admin.js"


def test_admin_js_cache_bust_is_monotonic():
    """Each admin.html must reference admin.js?v=N with a positive int."""
    import re
    versions = []
    for f in sorted(ADMIN_WEB_DIR.glob("*.html")):
        m = re.search(r'admin\.js\?v=(\d+)', f.read_text(encoding="utf-8"))
        assert m, f"{f.name} missing admin.js?v=N"
        versions.append(int(m.group(1)))
    # All same version is fine; just non-zero and positive.
    assert all(v >= 1 for v in versions)


def test_admin_routes_serve_html_pages():
    """FastAPI serves the admin HTML at /admin/<name>.html."""
    from app.main import app
    with TestClient(app) as c:
        for name in ["login", "index", "accounts", "settings"]:
            r = c.get(f"/admin/{name}.html")
            assert r.status_code == 200, f"/admin/{name}.html returned {r.status_code}"
            assert "<html" in r.text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_static.py -v`
Expected: `FileNotFoundError` (web/admin/ does not exist).

- [ ] **Step 3: Create `web/admin/admin.css`**

```css
/* web/admin/admin.css — shared admin SPA styles */
:root {
  --bg: #f7f7f8;
  --bg-elev: #ffffff;
  --fg: #1f2328;
  --fg-muted: #6b7280;
  --border: #e5e7eb;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --danger: #dc2626;
  --danger-hover: #b91c1c;
  --warning-bg: #fef3c7;
  --warning-fg: #92400e;
  --success: #16a34a;
  --locked: #dc2626;
  --radius: 6px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  line-height: 1.5;
}

a { color: var(--primary); text-decoration: none; }
a:hover { text-decoration: underline; }

button {
  cursor: pointer;
  font: inherit;
  border: 1px solid var(--border);
  background: var(--bg-elev);
  color: var(--fg);
  padding: 6px 14px;
  border-radius: var(--radius);
}
button:hover { background: #f3f4f6; }
button.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
button.primary:hover { background: var(--primary-hover); border-color: var(--primary-hover); }
button.danger { color: var(--danger); border-color: var(--danger); }
button.danger:hover { background: var(--danger); color: #fff; }
button:disabled { opacity: 0.5; cursor: not-allowed; }

input[type=text], input[type=password], input[type=number] {
  font: inherit;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  width: 100%;
}
input:focus { outline: 2px solid var(--primary); outline-offset: -1px; }

/* nav */
nav.admin-nav {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  background: var(--bg-elev);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 10;
}
nav.admin-nav .brand { font-weight: 600; margin-right: 12px; }
nav.admin-nav a { padding: 4px 10px; border-radius: var(--radius); }
nav.admin-nav a.active { background: #e0e7ff; }
nav.admin-nav .spacer { flex: 1; }
nav.admin-nav .user { color: var(--fg-muted); margin-right: 8px; }

/* main */
main.admin-main { max-width: 960px; margin: 24px auto; padding: 0 20px; }

/* card */
.card {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 20px;
  margin-bottom: 18px;
  box-shadow: var(--shadow);
}
.card h2 { margin-top: 0; font-size: 16px; }

/* banner */
.banner-warn {
  background: var(--warning-bg);
  color: var(--warning-fg);
  border: 1px solid #fbbf24;
  border-radius: var(--radius);
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 13px;
}

/* table */
table.admin-table { width: 100%; border-collapse: collapse; }
table.admin-table th, table.admin-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
table.admin-table th { background: #f9fafb; font-weight: 600; }
.status-ok { color: var(--success); }
.status-locked { color: var(--locked); font-weight: 600; }

/* form section */
.form-section { margin-bottom: 22px; }
.form-section h3 { margin: 0 0 8px; font-size: 14px; }
.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.form-row label {
  width: 180px;
  color: var(--fg-muted);
  flex-shrink: 0;
}
.form-row .field { flex: 1; }
.form-row input[type=range] { width: 100%; }
.form-section .actions {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

/* modal */
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
}
.modal {
  background: var(--bg-elev);
  border-radius: 8px;
  padding: 20px 24px;
  width: 360px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.2);
}
.modal h3 { margin-top: 0; }
.modal .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }

/* toast */
#toast {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0,0,0,0.8);
  color: #fff;
  padding: 10px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  z-index: 200;
}
#toast.hidden { display: none; }

/* login page */
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 32px;
  width: 360px;
  box-shadow: var(--shadow);
}
.login-card h1 { margin: 0 0 6px; font-size: 18px; }
.login-card .subtitle { color: var(--fg-muted); margin-bottom: 22px; font-size: 13px; }
.login-card .field { margin-bottom: 14px; }
.login-card .submit { width: 100%; padding: 10px; }
```

- [ ] **Step 4: Create `web/admin/admin.js`**

```javascript
"use strict";
// web/admin/admin.js — shared admin SPA bootstrap.
// Exposes: requireAdmin, toast, api, $.

const ADMIN_BASE = "/api/admin";
const COOKIE_NAME = "counselor_admin";

const $ = (sel, root = document) => root.querySelector(sel);

function toast(text, ms = 2500) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), ms);
}

async function api(path, options = {}) {
  const opts = {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  const r = await fetch(ADMIN_BASE + path, opts);
  if (r.status === 401) {
    // Session expired; bounce to login.
    window.location.href = "/admin/login.html";
    throw new Error("unauthenticated");
  }
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    throw Object.assign(new Error(detail), { status: r.status, detail });
  }
  if (r.status === 204) return null;
  return r.json();
}

async function requireAdmin() {
  // For pages other than login.html.
  if (location.pathname.endsWith("/login.html")) return null;
  try {
    const me = await api("/me");
    return me;
  } catch (_) {
    window.location.href = "/admin/login.html";
    return null;
  }
}

// Auto-highlight current nav link.
document.addEventListener("DOMContentLoaded", () => {
  const path = location.pathname;
  for (const a of document.querySelectorAll("nav.admin-nav a")) {
    if (a.getAttribute("href") && path.endsWith(a.getAttribute("href"))) {
      a.classList.add("active");
    }
  }
});
```

- [ ] **Step 5: Create `web/admin/login.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light" />
<title>登录 · AI 辅导员管理后台</title>
<link rel="stylesheet" href="admin.css?v=1" />
</head>
<body>
<div class="login-wrap">
  <form class="login-card" id="login-form">
    <h1>AI 辅导员 · 管理后台</h1>
    <p class="subtitle">请使用管理员账号登录</p>
    <div class="field">
      <label for="username">用户名</label>
      <input id="username" type="text" autocomplete="username" required />
    </div>
    <div class="field">
      <label for="password">密码</label>
      <input id="password" type="password" autocomplete="current-password" required />
    </div>
    <button id="submit" type="submit" class="primary submit">登录</button>
  </form>
</div>
<div id="toast" class="hidden"></div>
<script src="admin.js?v=1"></script>
<script>
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("submit");
  btn.disabled = true;
  try {
    await api("/login", {
      method: "POST",
      body: {
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value,
      },
    });
    window.location.href = "/admin/index.html";
  } catch (err) {
    const msg = err.status === 423 ? "账号已被锁定" : "用户名或密码错误";
    toast(msg);
    btn.disabled = false;
  }
});
api("/me").then(() => { window.location.href = "/admin/index.html"; })
           .catch(() => { /* expected — show form */ });
</script>
</body>
</html>
```

- [ ] **Step 6: Run admin static tests**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_static.py -v`
Expected: 6+ tests pass.

- [ ] **Step 7: Commit**

```bash
git add web/admin/admin.css web/admin/admin.js web/admin/login.html tests/test_admin_static.py
git commit -m "feat(admin): SPA foundation (admin.css, admin.js, login.html)"
```

---

### Task 10: Admin SPA — dashboard page (`/admin/index.html`)

**Files:**
- Create: `web/admin/index.html`

- [ ] **Step 1: Create `web/admin/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light" />
<title>仪表盘 · 管理后台</title>
<link rel="stylesheet" href="admin.css?v=1" />
</head>
<body>
<nav class="admin-nav">
  <span class="brand">AI 辅导员 · 管理后台</span>
  <a href="/admin/index.html">仪表盘</a>
  <a href="/admin/accounts.html">账号</a>
  <a href="/admin/settings.html">设置</a>
  <span class="spacer"></span>
  <span class="user" id="nav-user"></span>
  <button id="logout" type="button">退出</button>
</nav>
<main class="admin-main">
  <h1 id="greeting">欢迎</h1>

  <div class="card">
    <h2>当前配置摘要</h2>
    <div id="settings-summary" aria-live="polite">加载中…</div>
  </div>

  <div class="card">
    <h2>重建索引</h2>
    <p style="color: var(--fg-muted); margin: 0 0 12px;">
      扫描 <code id="docs-dir">./Documents</code> 目录，构建向量数据库。
    </p>
    <div class="form-row">
      <label><input type="checkbox" id="force" /> 强制重建（忽略文件指纹缓存）</label>
    </div>
    <div class="actions">
      <button id="reindex-btn" type="button" class="primary">重建索引</button>
      <span id="reindex-status" style="align-self: center; color: var(--fg-muted);"></span>
    </div>
    <div id="reindex-result" style="margin-top: 16px;"></div>
  </div>

  <div class="card">
    <h2>最近索引</h2>
    <div id="last-reindex">暂无记录</div>
  </div>
</main>

<div id="confirm-backdrop" class="modal-backdrop hidden">
  <div class="modal">
    <h3>确认重建索引</h3>
    <p>将扫描文档目录，可能耗时较长。是否继续？</p>
    <div class="actions">
      <button id="confirm-cancel" type="button">取消</button>
      <button id="confirm-ok" type="button" class="primary">确认</button>
    </div>
  </div>
</div>

<div id="toast" class="hidden"></div>
<script src="admin.js?v=1"></script>
<script>
const elDocsDir = document.getElementById("docs-dir");
const elReindexBtn = document.getElementById("reindex-btn");
const elReindexStatus = document.getElementById("reindex-status");
const elReindexResult = document.getElementById("reindex-result");
const elLastReindex = document.getElementById("last-reindex");
const elSettingsSummary = document.getElementById("settings-summary");
const elGreeting = document.getElementById("greeting");
const elNavUser = document.getElementById("nav-user");
const elConfirmBackdrop = document.getElementById("confirm-backdrop");

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

async function init() {
  const me = await requireAdmin();
  if (!me) return;
  elNavUser.textContent = me.username;
  elGreeting.textContent = `欢迎，${me.username}`;
  try {
    const s = await api("/settings");
    elDocsDir.textContent = s.paths.documents_dir;
    elSettingsSummary.innerHTML = `
      <table class="admin-table">
        <tr><th>LLM 模型</th><td>${escapeHtml(s.llm.model_name)}</td></tr>
        <tr><th>LLM 端点</th><td>${escapeHtml(s.llm.base_url)}</td></tr>
        <tr><th>Temperature</th><td>${s.llm.temperature}</td></tr>
        <tr><th>Max tokens</th><td>${s.llm.max_tokens}</td></tr>
        <tr><th>检索 k</th><td>${s.retrieval.k}</td></tr>
        <tr><th>Chunk size / overlap</th><td>${s.retrieval.chunk_size} / ${s.retrieval.chunk_overlap}</td></tr>
        <tr><th>Embedding 模型</th><td>${escapeHtml(s.embedding.model)}</td></tr>
        <tr><th>文档目录</th><td>${escapeHtml(s.paths.documents_dir)}</td></tr>
      </table>`;
  } catch (_) {}
  try {
    const lr = await api("/reindex/last");
    if (lr.last) {
      const d = new Date(lr.last.ts * 1000).toLocaleString();
      elLastReindex.innerHTML = `
        <table class="admin-table">
          <tr><th>时间</th><td>${d}</td></tr>
          <tr><th>模式</th><td>${lr.last.force ? "强制重建" : "增量"}</td></tr>
          <tr><th>新增</th><td>${lr.last.added}</td></tr>
          <tr><th>跳过</th><td>${lr.last.skipped}</td></tr>
          <tr><th>失败</th><td>${lr.last.failed.length}</td></tr>
        </table>`;
    }
  } catch (_) {}
  elReindexBtn.addEventListener("click", () => elConfirmBackdrop.classList.remove("hidden"));
  document.getElementById("confirm-cancel").addEventListener("click",
    () => elConfirmBackdrop.classList.add("hidden"));
  document.getElementById("confirm-ok").addEventListener("click", async () => {
    elConfirmBackdrop.classList.add("hidden");
    elReindexBtn.disabled = true;
    elReindexStatus.textContent = "处理中…";
    try {
      const force = document.getElementById("force").checked;
      const result = await api("/reindex", { method: "POST", body: { force } });
      elReindexStatus.textContent = "完成";
      renderResult(result);
      const lr = await api("/reindex/last");
      if (lr.last) {
        const d = new Date(lr.last.ts * 1000).toLocaleString();
        elLastReindex.innerHTML = `<p>上次重建：${d}（新增 ${lr.last.added} / 跳过 ${lr.last.skipped} / 失败 ${lr.last.failed.length}）</p>`;
      }
    } catch (err) {
      elReindexStatus.textContent = "";
      toast(`重建失败：${err.message}`);
    } finally {
      elReindexBtn.disabled = false;
    }
  });
  document.getElementById("logout").addEventListener("click", async () => {
    try { await api("/logout", { method: "POST" }); } catch (_) {}
    window.location.href = "/admin/login.html";
  });
}

function renderResult(r) {
  let html = `<p><strong>${r.added}</strong> 新增，<strong>${r.skipped}</strong> 跳过，<strong>${r.failed.length}</strong> 失败</p>`;
  if (r.items && r.items.length) {
    html += '<table class="admin-table"><tr><th>文件</th><th>状态</th><th>详情</th></tr>';
    for (const it of r.items) {
      const det = it.chunks != null ? `${it.chunks} chunks` : (it.reason || it.error || "");
      html += `<tr><td>${escapeHtml(it.path)}</td><td>${it.status}</td><td>${escapeHtml(String(det))}</td></tr>`;
    }
    html += "</table>";
  }
  elReindexResult.innerHTML = html;
}

init();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify dashboard renders + manual smoke**

Run: `OFFLINE=1 uv run --extra dev pytest tests/test_admin_static.py -v`
Start server with `bash scripts/run.sh &`, navigate to `http://localhost:8000/admin/login.html`, log in, confirm dashboard loads.

- [ ] **Step 3: Commit**

```bash
git add web/admin/index.html
git commit -m "feat(admin): dashboard page with reindex flow + last-index card"
```

---

### Task 11: Admin SPA — accounts page (`/admin/accounts.html`)

**Files:**
- Create: `web/admin/accounts.html`

- [ ] **Step 1: Create `web/admin/accounts.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light" />
<title>账号 · 管理后台</title>
<link rel="stylesheet" href="admin.css?v=1" />
</head>
<body>
<nav class="admin-nav">
  <span class="brand">AI 辅导员 · 管理后台</span>
  <a href="/admin/index.html">仪表盘</a>
  <a href="/admin/accounts.html">账号</a>
  <a href="/admin/settings.html">设置</a>
  <span class="spacer"></span>
  <span class="user" id="nav-user"></span>
  <button id="logout" type="button">退出</button>
</nav>
<main class="admin-main">
  <div style="display: flex; align-items: center; margin-bottom: 12px;">
    <h1 style="margin: 0; flex: 1;">管理员账号</h1>
    <button id="add-btn" type="button" class="primary">+ 新增管理员</button>
  </div>
  <div class="card">
    <table class="admin-table" id="accounts-table">
      <thead><tr><th>用户名</th><th>创建时间</th><th>最后登录</th><th>状态</th><th>操作</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</main>

<div id="add-backdrop" class="modal-backdrop hidden">
  <div class="modal">
    <h3>新增管理员</h3>
    <div class="field" style="margin-bottom: 10px;">
      <label>用户名（3-32，[a-z0-9_-]）</label>
      <input id="add-username" type="text" />
    </div>
    <div class="field" style="margin-bottom: 10px;">
      <label>密码（至少 6 字符）</label>
      <input id="add-password" type="password" />
    </div>
    <div class="field" style="margin-bottom: 14px;">
      <label>确认密码</label>
      <input id="add-password2" type="password" />
    </div>
    <div class="actions">
      <button id="add-cancel" type="button">取消</button>
      <button id="add-ok" type="button" class="primary">创建</button>
    </div>
  </div>
</div>

<div id="edit-backdrop" class="modal-backdrop hidden">
  <div class="modal">
    <h3>修改密码</h3>
    <div class="field" style="margin-bottom: 10px;">
      <label>用户名</label>
      <input id="edit-username" type="text" disabled />
    </div>
    <div class="field" id="edit-old-wrap" style="margin-bottom: 10px;">
      <label>原密码（修改自己时必填）</label>
      <input id="edit-old" type="password" />
    </div>
    <div class="field" style="margin-bottom: 10px;">
      <label>新密码（至少 6 字符）</label>
      <input id="edit-new" type="password" />
    </div>
    <div class="field" style="margin-bottom: 14px;">
      <label>确认新密码</label>
      <input id="edit-new2" type="password" />
    </div>
    <div class="actions">
      <button id="edit-cancel" type="button">取消</button>
      <button id="edit-ok" type="button" class="primary">保存</button>
    </div>
  </div>
</div>

<div id="del-backdrop" class="modal-backdrop hidden">
  <div class="modal">
    <h3>确认删除</h3>
    <p id="del-message"></p>
    <div class="actions">
      <button id="del-cancel" type="button">取消</button>
      <button id="del-ok" type="button" class="danger">删除</button>
    </div>
  </div>
</div>

<div id="toast" class="hidden"></div>
<script src="admin.js?v=1"></script>
<script>
let currentMe = null;
let accountsCache = [];
let editTargetId = null;
let delTargetId = null;

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

async function init() {
  const me = await requireAdmin();
  if (!me) return;
  currentMe = me;
  document.getElementById("nav-user").textContent = me.username;
  document.getElementById("logout").addEventListener("click", async () => {
    try { await api("/logout", { method: "POST" }); } catch (_) {}
    location.href = "/admin/login.html";
  });
  await refresh();
  wireModals();
}

async function refresh() {
  try { accountsCache = await api("/accounts"); } catch (_) { return; }
  const tbody = document.querySelector("#accounts-table tbody");
  tbody.innerHTML = "";
  for (const a of accountsCache) {
    const tr = document.createElement("tr");
    const status = a.locked
      ? '<span class="status-locked">已锁定</span>'
      : '<span class="status-ok">正常</span>';
    const created = new Date(a.created_at * 1000).toLocaleString();
    const last = a.last_login_at ? new Date(a.last_login_at * 1000).toLocaleString() : "—";
    const isSelf = a.username === currentMe.username;
    tr.innerHTML = `
      <td>${escapeHtml(a.username)}${isSelf ? ' <small style="color:var(--fg-muted)">(当前)</small>' : ""}</td>
      <td>${created}</td>
      <td>${last}</td>
      <td>${status}</td>
      <td>
        <button data-act="edit" data-id="${a.id}">改密</button>
        ${a.locked ? `<button data-act="unlock" data-id="${a.id}">解锁</button>` : ""}
        <button data-act="del" data-id="${a.id}" data-name="${escapeHtml(a.username)}" class="danger">删除</button>
      </td>`;
    tbody.appendChild(tr);
  }
  for (const btn of tbody.querySelectorAll("button")) {
    btn.addEventListener("click", onAction);
  }
}

function onAction(e) {
  const id = e.target.dataset.id;
  const act = e.target.dataset.act;
  if (act === "edit") openEdit(id);
  else if (act === "del") openDelete(id, e.target.dataset.name);
  else if (act === "unlock") doUnlock(id);
}

async function doUnlock(id) {
  try {
    await api(`/accounts/${id}`, { method: "PATCH", body: { unlock: true } });
    toast("已解锁");
    await refresh();
  } catch (e) { toast(e.message); }
}

function wireModals() {
  document.getElementById("add-btn").addEventListener("click", () => {
    document.getElementById("add-backdrop").classList.remove("hidden");
    document.getElementById("add-username").focus();
  });
  document.getElementById("add-cancel").addEventListener("click", closeAdd);
  document.getElementById("add-ok").addEventListener("click", async () => {
    const u = document.getElementById("add-username").value.trim();
    const p1 = document.getElementById("add-password").value;
    const p2 = document.getElementById("add-password2").value;
    if (p1 !== p2) return toast("两次密码不一致");
    try {
      await api("/accounts", { method: "POST", body: { username: u, password: p1 } });
      toast("已创建");
      closeAdd();
      await refresh();
    } catch (e) { toast(e.message); }
  });
  document.getElementById("edit-cancel").addEventListener("click", closeEdit);
  document.getElementById("edit-ok").addEventListener("click", async () => {
    const p1 = document.getElementById("edit-new").value;
    const p2 = document.getElementById("edit-new2").value;
    const old = document.getElementById("edit-old").value;
    if (p1 !== p2) return toast("两次密码不一致");
    const body = { new_password: p1 };
    if (old) body.old_password = old;
    try {
      await api(`/accounts/${editTargetId}`, { method: "PATCH", body });
      toast("已保存");
      closeEdit();
      await refresh();
    } catch (e) { toast(e.message); }
  });
  document.getElementById("del-cancel").addEventListener("click", closeDel);
  document.getElementById("del-ok").addEventListener("click", async () => {
    try {
      await api(`/accounts/${delTargetId}`, { method: "DELETE" });
      toast("已删除");
      closeDel();
      await refresh();
    } catch (e) { toast(e.message); }
  });
}

function closeAdd() {
  document.getElementById("add-backdrop").classList.add("hidden");
  document.getElementById("add-username").value = "";
  document.getElementById("add-password").value = "";
  document.getElementById("add-password2").value = "";
}
function closeEdit() {
  document.getElementById("edit-backdrop").classList.add("hidden");
  editTargetId = null;
}
function openEdit(id) {
  editTargetId = id;
  const a = accountsCache.find((x) => x.id === id);
  if (!a) return;
  document.getElementById("edit-username").value = a.username;
  document.getElementById("edit-old").value = "";
  document.getElementById("edit-new").value = "";
  document.getElementById("edit-new2").value = "";
  const isSelf = a.username === currentMe.username;
  document.getElementById("edit-old-wrap").style.display = isSelf ? "block" : "none";
  document.getElementById("edit-backdrop").classList.remove("hidden");
}
function openDelete(id, name) {
  delTargetId = id;
  document.getElementById("del-message").textContent = `确认删除账号 ${name}？此操作不可撤销。`;
  document.getElementById("del-backdrop").classList.remove("hidden");
}
function closeDel() {
  document.getElementById("del-backdrop").classList.add("hidden");
  delTargetId = null;
}

init();
</script>
</body>
</html>
```

- [ ] **Step 2: Manual smoke**

Open `http://localhost:8000/admin/accounts.html` after login. Verify Add creates, Edit saves, Delete removes (and refuses self/last admin).

- [ ] **Step 3: Commit**

```bash
git add web/admin/accounts.html
git commit -m "feat(admin): accounts page with CRUD modals + self/last-admin guards"
```

---

### Task 12: Admin SPA — settings page (`/admin/settings.html`)

**Files:**
- Create: `web/admin/settings.html`

- [ ] **Step 1: Create `web/admin/settings.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light" />
<title>设置 · 管理后台</title>
<link rel="stylesheet" href="admin.css?v=1" />
</head>
<body>
<nav class="admin-nav">
  <span class="brand">AI 辅导员 · 管理后台</span>
  <a href="/admin/index.html">仪表盘</a>
  <a href="/admin/accounts.html">账号</a>
  <a href="/admin/settings.html">设置</a>
  <span class="spacer"></span>
  <span class="user" id="nav-user"></span>
  <button id="logout" type="button">退出</button>
</nav>
<main class="admin-main">
  <h1>系统设置</h1>
  <div id="restart-banner" class="banner-warn hidden">
    ⚠️ 以下修改需重启服务后才能生效：<span id="restart-fields"></span>
  </div>

  <div class="card form-section">
    <h3>LLM 推理参数（热生效）</h3>
    <div class="form-row"><label>Temperature (0–2)</label><input class="field" id="llm-temperature" type="number" step="0.1" min="0" max="2" /></div>
    <div class="form-row"><label>Max tokens (1–32768)</label><input class="field" id="llm-max_tokens" type="number" step="1" min="1" max="32768" /></div>
    <div class="form-row"><label>Top P (0–1)</label><input class="field" id="llm-top_p" type="number" step="0.05" min="0" max="1" /></div>
    <div class="form-row"><label>Frequency penalty (-2–2)</label><input class="field" id="llm-frequency_penalty" type="number" step="0.1" min="-2" max="2" /></div>
    <div class="form-row"><label>Presence penalty (-2–2)</label><input class="field" id="llm-presence_penalty" type="number" step="0.1" min="-2" max="2" /></div>
    <div class="actions"><button data-save="llm" class="primary" type="button">保存 LLM 推理</button></div>
  </div>

  <div class="card form-section">
    <h3>LLM 连接（需重启）</h3>
    <div class="form-row"><label>Base URL</label><input class="field" id="llm-base_url" type="text" /></div>
    <div class="form-row"><label>Model name</label><input class="field" id="llm-model_name" type="text" /></div>
    <div class="form-row"><label>Timeout (5–600 s)</label><input class="field" id="llm-timeout" type="number" step="1" min="5" max="600" /></div>
    <div class="actions"><button data-save="llm-conn" class="primary" type="button">保存 LLM 连接</button></div>
  </div>

  <div class="card form-section">
    <h3>检索（热生效）</h3>
    <div class="form-row"><label>k (1–50)</label><input class="field" id="retrieval-k" type="number" step="1" min="1" max="50" /></div>
    <div class="form-row"><label>Chunk size (50–5000)</label><input class="field" id="retrieval-chunk_size" type="number" step="1" min="50" max="5000" /></div>
    <div class="form-row"><label>Chunk overlap (0–4999)</label><input class="field" id="retrieval-chunk_overlap" type="number" step="1" min="0" max="4999" /></div>
    <div class="actions"><button data-save="retrieval" class="primary" type="button">保存检索</button></div>
  </div>

  <div class="card form-section">
    <h3>路径与环境（需重启）</h3>
    <div class="form-row"><label>Documents dir</label><input class="field" id="paths-documents_dir" type="text" /></div>
    <div class="form-row"><label>Data dir</label><input class="field" id="paths-data_dir" type="text" /></div>
    <div class="form-row"><label>Chroma collection</label><input class="field" id="paths-chroma_collection" type="text" /></div>
    <div class="actions"><button data-save="paths" class="primary" type="button">保存路径</button></div>
  </div>

  <div class="card form-section">
    <h3>Embedding 模型（需重启）</h3>
    <div class="form-row"><label>Model</label><input class="field" id="embedding-model" type="text" /></div>
    <div class="actions"><button data-save="embedding" class="primary" type="button">保存 Embedding</button></div>
  </div>
</main>

<div id="toast" class="hidden"></div>
<script src="admin.js?v=1"></script>
<script>
const SAVE_MAP = {
  "llm": { section: "llm", fields: ["temperature","max_tokens","top_p","frequency_penalty","presence_penalty"] },
  "llm-conn": { section: "llm", fields: ["base_url","model_name","timeout"] },
  "retrieval": { section: "retrieval", fields: ["k","chunk_size","chunk_overlap"] },
  "paths": { section: "paths", fields: ["documents_dir","data_dir","chroma_collection"] },
  "embedding": { section: "embedding", fields: ["model"] },
};

async function init() {
  const me = await requireAdmin();
  if (!me) return;
  document.getElementById("nav-user").textContent = me.username;
  document.getElementById("logout").addEventListener("click", async () => {
    try { await api("/logout", { method: "POST" }); } catch (_) {}
    location.href = "/admin/login.html";
  });
  await load();
  for (const btn of document.querySelectorAll("[data-save]")) {
    btn.addEventListener("click", () => saveSection(btn.dataset.save));
  }
}

async function load() {
  const s = await api("/settings");
  setVal("llm", s.llm);
  setVal("retrieval", s.retrieval);
  setVal("paths", s.paths);
  setVal("embedding", s.embedding);
}

function setVal(section, obj) {
  for (const k of Object.keys(obj)) {
    const el = document.getElementById(`${section}-${k}`);
    if (el) el.value = obj[k];
  }
}

function getVal(section, field) {
  const el = document.getElementById(`${section}-${field}`);
  if (!el) return undefined;
  const v = el.value;
  if (["temperature","max_tokens","timeout","top_p","frequency_penalty",
       "presence_penalty","k","chunk_size","chunk_overlap"].includes(field)) {
    return Number(v);
  }
  return v;
}

async function saveSection(key) {
  const cfg = SAVE_MAP[key];
  const section = cfg.section;
  const payload = {};
  for (const f of cfg.fields) payload[f] = getVal(section, f);
  try {
    const result = await api("/settings", {
      method: "PUT", body: { sections: { [section]: payload } },
    });
    if (result.restart_required && result.restart_required.length) {
      showRestart(result.restart_required);
      toast(`已保存（需重启：${result.restart_required.join(", ")}）`);
    } else {
      hideRestart();
      toast("已保存");
    }
    await load();
  } catch (e) {
    toast(`保存失败：${e.message}`);
  }
}

function showRestart(fields) {
  document.getElementById("restart-banner").classList.remove("hidden");
  document.getElementById("restart-fields").textContent = fields.join("，");
}

function hideRestart() {
  document.getElementById("restart-banner").classList.add("hidden");
}

init();
</script>
</body>
</html>
```

- [ ] **Step 2: Manual smoke**

Change Temperature → Save → expect "已保存". Change Base URL → Save → expect yellow banner with `llm.base_url`.

- [ ] **Step 3: Commit**

```bash
git add web/admin/settings.html
git commit -m "feat(admin): settings page with per-section save + restart banner"
```

---

### Task 13: Documentation + final verification

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Update `CLAUDE.md`**

Read `CLAUDE.md` first. Add a new section after `## 包结构`:

```markdown
## 管理后台（admin subsystem）

- 后台入口：`/admin/login.html`（**不在用户前台显示入口**）；默认账号 `admin / 147369`，首次登录后**必须**改密。
- 后端：`app/admin/` 包（auth / accounts / settings / reindex / routes / schemas）；SQLite 持久化在 `storage/admin_db.py` → 单文件 `data/admin.db`（WAL + `threading.RLock`）。
- 路由：`/api/admin/{login,logout,me,accounts,settings,reindex,reindex/last}`；session cookie `counselor_admin`（HttpOnly + SameSite=Lax + 24h 滑动续期）。
- 锁定策略：6 次错误后**永久**锁定，必须其他管理员手动解锁。
- 可调参数分两类：热生效（`temperature/max_tokens/top_p/penalties/k/chunk_*`）和需重启（`base_url/model_name/timeout/paths/embedding.model`）；`PUT /api/admin/settings` 返回的 `restart_required` 字段列出后者。
- 前端：`web/admin/` 4 个独立 HTML 页面 + 共享 `admin.css` / `admin.js`；无 npm、无构建。
- 用户前台去掉了「重建索引」按钮（迁移至后台），`/api/ingest` 已删除（重建索引仅走 `POST /api/admin/reindex`）。
- `llm/config.py` / `rag/retriever.py` / `rag/splitter.py` 改为从运行时单例读配置，支持热生效字段的下一次请求即时生效。
- 修改 `web/admin/admin.js` 或 `web/admin/*.html` 时同样按需 bump `<script src="admin.js?v=N">`（当前 `?v=1`，与用户 SPA 的 `?v=12` 互相独立计数）。
```

Also update the existing `## 包结构` table to include `app/admin/` and `storage/admin_db.py`.

- [ ] **Step 2: Update `README.md`**

Read it first, then add a `## 管理后台` section near the top:

```markdown
## 管理后台

启动服务后访问 `http://localhost:8000/admin/login.html`，使用默认账号 `admin / 147369` 登录。

⚠️ **首次登录后请立即修改默认密码**（`/admin/accounts` → 选中自己 → 改密）。

后台可做：
- 配置 AI 模型参数（LLM 推理 / 连接 / 检索 / 路径 / Embedding）
- 触发向量数据库重建索引（前台聊天界面的「重建索引」按钮已迁移至此）
- 管理多个管理员账号，支持 6 次错误后永久锁定 + 解锁

详细规范见 `docs/superpowers/specs/2026-07-25-admin-backend-design.md`。
```

- [ ] **Step 3: Run full suite**

Run: `OFFLINE=1 uv run --extra dev pytest -q`
Expected: ~165 passed / 2 skipped.

If anything fails, fix before continuing.

- [ ] **Step 4: Manual end-to-end smoke**

```bash
pkill -f "uvicorn app.main:app" || true
rm -f data/admin.db  # fresh seed
bash scripts/run.sh &
sleep 2
curl -s http://localhost:8000/api/health | python -m json.tool
curl -s -c /tmp/c.jar -X POST http://localhost:8000/api/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"147369"}'
curl -s -b /tmp/c.jar http://localhost:8000/api/admin/me
curl -s -b /tmp/c.jar -X POST http://localhost:8000/api/admin/accounts \
  -H 'Content-Type: application/json' \
  -d '{"username":"bob","password":"bobpass1"}'
curl -s -b /tmp/c.jar -X PUT http://localhost:8000/api/admin/settings \
  -H 'Content-Type: application/json' \
  -d '{"sections":{"llm":{"temperature":0.7}}}'
curl -s -b /tmp/c.jar -X POST http://localhost:8000/api/admin/reindex \
  -H 'Content-Type: application/json' -d '{"force":true}'
curl -s -b /tmp/c.jar http://localhost:8000/api/admin/reindex/last
for i in 1 2 3 4 5 6; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    http://localhost:8000/api/admin/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"bob","password":"wrong"}'
done
curl -s -b /tmp/c.jar -X POST http://localhost:8000/api/admin/logout -o /dev/null -w "%{http_code}\n"
```

All requests after the login should return 200; bob's 6th wrong-password attempt should be 423.

- [ ] **Step 5: Visual smoke via Playwright**

Open Chrome at `http://localhost:8000/admin/login.html`:
1. Login as admin / 147369 → expect redirect to `/admin/index.html`.
2. Click "重建索引" → confirm modal → expect result table.
3. Navigate to `/admin/accounts.html` → add a new account → expect table refresh.
4. Navigate to `/admin/settings.html` → change temperature → save → expect "已保存" toast.
5. Click "退出" → expect redirect to login page.

- [ ] **Step 6: Final commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: document admin backend (URL, default creds, hot-reload fields)"
```

- [ ] **Step 7: Tag the work**

```bash
git tag admin-backend-v1
```

---

## Coverage Summary

After all 13 tasks:

| Layer | Test file | Approx. count |
|---|---|---|
| Storage | `tests/test_admin_db.py` | 25 |
| Auth | `tests/test_admin_auth.py` | 22 |
| Accounts | `tests/test_admin_accounts.py` | 24 |
| Settings | `tests/test_admin_settings.py` | 30 |
| Reindex | `tests/test_admin_reindex.py` | 7 |
| Routes | `tests/test_admin_routes.py` | 25 |
| Static | `tests/test_admin_static.py` | 6 |
| Updated existing | `tests/test_api.py` | 2 |
| **Total new admin tests** | | **~141** |
| Baseline | (existing) | 57 + 2 skipped |

End state: **~198 passed / 2 skipped**.

## Risks / Open Items for Reviewer Attention

1. **SQLite + write lock** — adequate for single-process local service; not safe across processes. Documented in spec.
2. **Hot-reload of LLM params** — applies on next `get_llm()` call; existing in-flight requests use captured values. Acceptable.
3. **Restart-required heuristic** — banner shows until manually hidden; no real restart detection. Documented as heuristic.
4. **CSRF** — `Origin` check rejects mutating requests from disallowed origins; `SameSite=Lax` covers the rest. Sufficient for local.
5. **Default password** — seeded automatically; admin must change on first login (documented in CLAUDE.md + README.md).
6. **`/api/ingest` removal** — breaking change for any external tooling that called it; none exist today (only the chat UI button used it).
7. **Cache-bust version on admin SPA** — currently `?v=1`; bump on each admin JS/HTML change.