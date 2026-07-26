"""Tests for app/admin/accounts.py — CRUD business logic + self-protection rules."""
from __future__ import annotations

import pytest

from app.admin import accounts as accts
from app.admin.accounts import (
    AccountNotFoundError,
    InvalidUsernameError,
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


def test_delete_only_admin_via_self_delete_raises_self_delete_error():
    """Self-delete subsumes the only-admin guard for the seeded default admin."""
    admin = db_accounts.get_by_username("admin")
    with pytest.raises(SelfDeleteError):
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
