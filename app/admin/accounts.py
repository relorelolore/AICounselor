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
