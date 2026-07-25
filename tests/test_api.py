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


def test_ingest_runs_with_empty_corpus(client):
    r = client.post("/api/ingest", json={"force": False})
    assert r.status_code == 200
    data = r.json()
    assert "added" in data and "skipped" in data and "failed" in data
    assert data["added"] == 0
    assert data["skipped"] == 0


def test_frontend_health_requests_have_timeouts(client):
    app_js = client.get("/app.js").text
    assert 'fetchWithTimeout("/api/health", {}, 3000)' in app_js
    assert 'fetchWithTimeout("/api/ingest", {' in app_js
    assert "}, 30000);" in app_js
    assert 'e.name === "AbortError" ? "连接超时"' in app_js


def test_frontend_script_is_cache_busted(client):
    index_html = client.get("/").text
    assert '<script src="app.js?v=6"></script>' in index_html


def test_frontend_clears_citations_on_new_send(client):
    """Regression: 每次发新问题要立刻清空「参考资料」面板，避免上一轮的
    citations 一直挂着显示。`appendCitations([])` 必须在 `sendMessage`
    创建 WebSocket 之前调用一次。"""
    app_js = client.get("/app.js").text
    # 文件里 appendCitations([]) 和 new WebSocket(url) 都唯一，
    # 位置约束即"清空必须在开 WebSocket 之前"。
    clear_idx = app_js.index("appendCitations([])")
    ws_idx = app_js.index("new WebSocket(url)")
    assert clear_idx < ws_idx, (
        "appendCitations([]) 必须在 sendMessage 创建 WebSocket 之前调用，"
        "否则上一轮的 citations 会跟着新问题一起显示。"
    )


def test_static_files_have_no_store_cache_header(client):
    """前端静态文件应带 ``Cache-Control: no-store``，强制浏览器每次拿最新
    版本，避免改了 app.js 但浏览器仍跑老 JS 的问题。"""
    for path in ("/", "/app.js", "/style.css"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        assert r.headers.get("cache-control") == "no-store", (
            f"{path} 缺少 Cache-Control: no-store 头；浏览器会缓存旧 JS 导致 "
            f"改前端代码后看不到效果"
        )
