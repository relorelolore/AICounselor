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
        if new_count == MAX_FAILED_ATTEMPTS:
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
