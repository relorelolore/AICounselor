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
    不能让会话列表只活在内存里——刷新页面应当看得到。

    Bind the literal to the constant: we require the *exact declaration*
    ``const STORAGE_KEY = "counselor:state"`` so a refactor that changes the
    literal (e.g. ``STORAGE_KEY = "wrong-key"``) can't silently pass while still
    satisfying `getItem`/`setItem` against `STORAGE_KEY`.
    """
    app_js = client.get("/app.js").text
    # 实际源码将 localStorage key 抽到了 STORAGE_KEY 常量（避免散落字符串）。
    # 这里把常量的「定义」与「使用」绑在一起：定义必须是 ``STORAGE_KEY =
    # "counselor:state"``（任何重命名 / 改字面量都会失败），后续读 / 写都要走
    # 同一个常量。
    assert 'STORAGE_KEY = "counselor:state"' in app_js, (
        "app.js 必须将 STORAGE_KEY 显式声明为 'counselor:state'，"
        "而不是散落的字符串字面量（否则 key 漂移时测试仍能假绿）"
    )
    assert "localStorage.getItem(STORAGE_KEY)" in app_js, (
        "app.js 应通过 STORAGE_KEY 读取多会话状态（store.load）"
    )
    assert "localStorage.setItem(STORAGE_KEY" in app_js, (
        "app.js 应通过 STORAGE_KEY 写入多会话状态（store.save）"
    )


def test_frontend_sends_full_history_per_request(client):
    """每次发消息必须把当前会话的完整历史（不只本轮）发给后端，让后端
    SqliteSaver / graph 在已持久化状态下推理；纯 session_id 模式不够。

    Bind the WS open-frame payload shape exactly: assert the real
    ``JSON.stringify({ session_id: sessionId, history })`` expression so a
    rename (e.g. ``msgs: history``) or dropping `history` from the payload
    fails this test.
    """
    app_js = client.get("/app.js").text
    # WS open 帧的 payload 必须是 ``JSON.stringify({ session_id: sessionId,
    # history })`` —— 把 ``history`` 改名为 ``msgs`` / ``messages`` / 删掉都会
    # 让这条断言失败，避免靠松散的 sentinel 假绿。
    assert "JSON.stringify({ session_id: sessionId, history })" in app_js, (
        "app.js 必须在 WS open 帧里 JSON.stringify 出 "
        "`{ session_id: sessionId, history }`，把完整历史发给后端"
    )


def test_frontend_has_sidebar_and_toggle(client):
    """ChatGPT 风格的侧边栏：会话列表 + 折叠按钮 + 新建按钮必须都在首页
    HTML 里（即便 JS 渲染失败也不应消失）。"""
    html = client.get("/").text
    assert 'id="sidebar"' in html
    assert 'id="sidebar-toggle"' in html
    assert 'id="chat-list"' in html
    assert 'id="new-chat-btn"' in html


def test_frontend_cache_bust_is_v7(client):
    """app.js 必须带 cache-bust 参数（每次发布 bump 版本号）避免浏览器
    缓存旧 JS。Review-fix wave 把 v=6 升到 v=7（移动端侧边栏修复）；后续 bump 时同步更新。"""
    html = client.get("/").text
    assert '<script src="app.js?v=7"></script>' in html


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
