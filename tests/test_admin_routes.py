# tests/test_admin_routes.py
"""Integration tests for app/admin/routes.py — FastAPI HTTP integration."""
from __future__ import annotations

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
    # httpx/TestClient doesn't auto-set Origin; set a default that matches
    # the route's _ALLOWED_ORIGIN (http://localhost:8000) so mutating
    # requests pass the CSRF check unless a test explicitly overrides Origin.
    with TestClient(app, headers={"Origin": "http://localhost:8000"}) as c:
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
    # llm.* fields are now all hot-reloadable (base_url included). restart_required
    # should be empty for llm-only updates; use paths.documents_dir to exercise the
    # restart-required path.
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"temperature": 0.5, "base_url": "http://x:1/v1"}}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["restart_required"] == []
    # Re-read:
    r2 = logged_in.get("/api/admin/settings")
    assert r2.json()["llm"]["temperature"] == 0.5
    assert r2.json()["llm"]["base_url"] == "http://x:1/v1"

    # paths.documents_dir is genuinely restart-required.
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"paths": {"documents_dir": "./new"}}},
    )
    assert r.status_code == 200
    assert "paths.documents_dir" in r.json()["restart_required"]


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
    # The route returns {"last": summary}; summary has "added" inside.
    assert r.json()["last"]["added"] == 5


def test_reindex_last_returns_null_before_any_run(logged_in):
    r = logged_in.get("/api/admin/reindex/last")
    assert r.status_code == 200
    assert r.json()["last"] is None


# ----- CSRF / Origin -----

def test_post_with_origin_matching_request_host_allowed(logged_in, monkeypatch):
    """Origin that matches the request's Host header is allowed even when
    the env-var _ALLOWED_ORIGIN differs (covers localhost/127.0.0.1/LAN-IP
    access without per-host env config)."""
    from app.admin import reindex
    monkeypatch.setattr(reindex, "build_index",
                        lambda *, force=False: {"added": 0, "skipped": 0,
                                                 "failed": [], "items": [],
                                                 "meta_written": True})
    r = logged_in.post(
        "/api/admin/reindex",
        json={"force": False},
        headers={"Origin": "http://testserver", "Host": "testserver"},
    )
    assert r.status_code == 200


def test_post_with_origin_mismatching_host_rejected(logged_in, monkeypatch):
    """Origin whose host:port differs from request Host is rejected."""
    from app.admin import reindex
    monkeypatch.setattr(reindex, "build_index",
                        lambda *, force=False: {"added": 0, "skipped": 0,
                                                 "failed": [], "items": [],
                                                 "meta_written": True})
    r = logged_in.post(
        "/api/admin/reindex",
        json={"force": False},
        headers={"Origin": "http://evil.example.com", "Host": "testserver"},
    )
    assert r.status_code == 403


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


# ----- /settings api_key -----

def test_settings_round_trip_api_key(logged_in, monkeypatch):
    """PUT → DB → GET → 单例：api_key 端到端走通且热生效。"""
    import importlib, llm.config as llm_cfg

    # 确保起点干净
    importlib.reload(llm_cfg)
    assert llm_cfg.get_llm_settings().api_key == "llama.cpp"

    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"api_key": "sk-test-abc"}}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sections"]["llm"]["api_key"] == "sk-test-abc"
    # Not restart-required (hot-reload).
    assert "llm.api_key" not in body["restart_required"]

    # GET 回显
    g = logged_in.get("/api/admin/settings")
    assert g.status_code == 200
    assert g.json()["llm"]["api_key"] == "sk-test-abc"

    # 单例 hot-reload
    assert llm_cfg.get_llm_settings().api_key == "sk-test-abc"


def test_settings_api_key_validation_empty_string(logged_in):
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"api_key": ""}}},
    )
    assert r.status_code == 400, r.text


def test_settings_api_key_validation_wrong_type(logged_in):
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"api_key": 123}}},
    )
    assert r.status_code == 400, r.text


def test_settings_api_key_not_restart_required(logged_in):
    """只改 api_key 时 restart_required 列表为空。"""
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"api_key": "sk-xyz"}}},
    )
    assert r.status_code == 200
    assert r.json()["restart_required"] == []
