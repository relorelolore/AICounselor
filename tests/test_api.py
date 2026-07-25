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


def test_frontend_uses_localstorage_for_history(client):
    """多会话前端必须用 localStorage 持久化会话状态（key ``counselor:state``），
    不能让会话列表只活在内存里——刷新页面应当看得到。"""
    app_js = client.get("/app.js").text
    # 实际源码将 localStorage key 抽到了 STORAGE_KEY 常量（避免散落字符串）。
    assert '"counselor:state"' in app_js, (
        "app.js 应定义 counselor:state 作为多会话状态的 localStorage key"
    )
    assert "localStorage.getItem(STORAGE_KEY)" in app_js, (
        "app.js 应通过 STORAGE_KEY 读取多会话状态（store.load）"
    )
    assert "localStorage.setItem(STORAGE_KEY" in app_js, (
        "app.js 应通过 STORAGE_KEY 写入多会话状态（store.save）"
    )


def test_frontend_sends_full_history_per_request(client):
    """每次发消息必须把当前会话的完整历史（不只本轮）发给后端，让后端
    SqliteSaver / graph 在已持久化状态下推理；纯 session_id 模式不够。"""
    app_js = client.get("/app.js").text
    # WS open 帧的 payload 形如 ``{ session_id: ..., history }``。
    # 这里采用对象简写，源码里 history 不带引号，作为 sentinel 验证。
    assert "history }" in app_js, (
        "app.js 应在 WS open 帧里把 history 一起发给后端（多会话无状态模型）"
    )


def test_frontend_has_sidebar_and_toggle(client):
    """ChatGPT 风格的侧边栏：会话列表 + 折叠按钮 + 新建按钮必须都在首页
    HTML 里（即便 JS 渲染失败也不应消失）。"""
    html = client.get("/").text
    assert 'id="sidebar"' in html
    assert 'id="sidebar-toggle"' in html
    assert 'id="chat-list"' in html
    assert 'id="new-chat-btn"' in html


def test_frontend_cache_bust_is_v6(client):
    """app.js 必须带 cache-bust 参数（每次发布 bump 版本号）避免浏览器
    缓存旧 JS。Task 5 把 v=5 升到 v=6；后续 bump 时同步更新。"""
    html = client.get("/").text
    assert '<script src="app.js?v=6"></script>' in html


def test_frontend_includes_citation_drawer(client):
    """「参考资料」抽屉（drawer）的壳必须在首屏 HTML 里就位，drawer 的内容
    由 JS 动态填充，但骨架由服务器渲染以降低首屏交互延迟。"""
    html = client.get("/").text
    assert 'id="drawer"' in html
    assert 'id="drawer-body"' in html


def test_frontend_drops_old_session_storage(client):
    """旧版单一 session_id 走 localStorage 的代码应彻底移除（新版本
    session_id 仅作为 WS 帧字段出现，不再持久化）。"""
    app_js = client.get("/app.js").text
    # localStorage 读写 session_id 的旧模式必须消失：
    assert 'localStorage.getItem("session_id")' not in app_js
    assert 'localStorage.setItem("session_id"' not in app_js
