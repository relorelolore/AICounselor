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
