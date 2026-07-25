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
