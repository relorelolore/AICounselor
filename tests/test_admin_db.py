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
    sess1 = sessions.get(sid1)
    # Create sid2 later so only sid1 is expired at the cleanup time.
    monkeypatch.setattr(admin_db.time, "time", lambda: sess1["expires_at"] + 2)
    sid2 = sessions.create(a["id"])
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
    assert kv.get("missing") is None


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
