# tests/test_api.py
import os
from fastapi.testclient import TestClient
import pytest


def test_health_returns_struct(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "chroma_count" in data
    assert "llm" in data
    assert data["status"] in ("ok", "degraded")


def test_index_served_with_no_store(client):
    """SPA 入口 index.html 应带 ``Cache-Control: no-store``，强制浏览器每次拿最新
    版本，避免更新构建产物后浏览器仍跑老 JS。"""
    r = client.get("/")
    assert r.status_code == 200
    assert '<div id="app">' in r.text
    assert r.headers.get("cache-control") == "no-store", (
        "/ 缺少 Cache-Control: no-store 头；浏览器会缓存旧 JS 导致 "
        "改前端代码后看不到效果"
    )


def test_hashed_assets_also_no_store(client):
    """构建出的 hash 资源（/assets/*）也应可访问。"""
    index = client.get("/").text
    import re

    m = re.search(r'src="(/assets/[^"]+\.js)"', index)
    assert m, "index.html 未引用 /assets/ 下的 JS bundle（dist 未构建？）"
    r = client.get(m.group(1))
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"


def test_spa_history_fallback_for_admin_routes(client):
    """管理后台是 Vue Router 前端路由：直达 /admin、/admin/login、
    /admin/settings 都应返回 SPA 入口（由前端路由接管渲染）。"""
    for path in ("/admin", "/admin/", "/admin/login", "/admin/accounts", "/admin/settings"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        assert '<div id="app">' in r.text, f"{path} 未返回 SPA 入口"


def test_spa_fallback_does_not_swallow_api_404(client):
    """/api/* 未知路径仍返回 404（API 标准行为），不被 SPA fallback 接管。"""
    r = client.get("/api/no-such-endpoint")
    assert r.status_code == 404
    r = client.post("/api/ingest", json={"force": False})
    assert r.status_code == 404


def test_spa_fallback_get_only(client):
    """fallback 只处理 GET/HEAD；其他方法打到未知路径不应返回 index.html。"""
    r = client.post("/some/random/path")
    assert r.status_code != 200 or '<div id="app">' not in r.text
