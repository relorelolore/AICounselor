# app/admin/routes.py
"""FastAPI router for /api/admin/* — auth + accounts + settings + reindex."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from storage import admin_db
from storage.admin_db import accounts as db_accounts

from . import accounts as accts
from . import auth
from . import reindex as reindex_svc
from . import settings as settings_svc
from .schemas import (
    AccountCreate,
    AccountUpdate,
    LoginRequest,
    ReindexRequest,
    SettingsPatch,
)


router = APIRouter()


_ALLOWED_ORIGIN = os.environ.get(
    "COUNSELOR_ALLOWED_ORIGIN", "http://localhost:8000"
)


def _check_origin(request: Request) -> None:
    """Reject mutating requests from disallowed origins (CSRF defense).

    GET/HEAD/OPTIONS are exempt.

    Origin is allowed if it matches either:
      (a) `COUNSELOR_ALLOWED_ORIGIN` env var (default `http://localhost:8000`), or
      (b) the request's own Host header (`http://<host>:<port>`) — this handles
          browsers that connect via `127.0.0.1` / `localhost` / LAN IP / etc.
          without requiring the admin to set the env var per host.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if origin is None:
        # Same-origin POST from a form could omit Origin in some browsers,
        # but for a JSON API with credentials=include, Origin is required.
        # We choose to be strict and reject.
        raise HTTPException(status_code=403, detail="origin header required")
    candidate = origin.rstrip("/")
    # (a) explicit env-var allow-list
    if candidate == _ALLOWED_ORIGIN.rstrip("/"):
        return
    # (b) same-host: the browser's Origin host:port must match the request's Host
    host = request.headers.get("host")
    if host and candidate == f"http://{host}":
        return
    raise HTTPException(status_code=403, detail="origin not allowed")


async def require_session(request: Request) -> dict:
    """Validate session cookie and return {account_id, username}."""
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
def logout(
    request: Request,
    response: Response,
    _=Depends(require_session),
) -> Response:
    sid = request.cookies.get(auth.SESSION_COOKIE_NAME)
    if sid:
        auth.delete_session(sid)
    response.delete_cookie(auth.SESSION_COOKIE_NAME, path="/")
    response.status_code = 204
    return response


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
            username=req.username,
            password=req.password,
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
    from llm.config import (
        update_embedding_settings,
        update_llm_settings,
        update_rag_settings,
    )
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
