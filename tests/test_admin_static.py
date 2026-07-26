"""Smoke tests for the built Vue SPA static bundle (web/dist)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"


def test_dist_dir_exists():
    assert DIST_DIR.is_dir(), (
        "web/dist 不存在 —— 请先在 frontend/ 下执行 `pnpm install && pnpm build`"
    )


def test_dist_has_index_and_hashed_assets():
    assert (DIST_DIR / "index.html").is_file()
    index = (DIST_DIR / "index.html").read_text(encoding="utf-8")
    assert '<div id="app">' in index
    # Vite 构建产物应引用带 content-hash 的 JS/CSS（取代旧前端手工 ?v=N 版本号）
    assert re.search(r'/assets/[^"]+-[\w-]{8,}\.js', index), (
        "index.html 未引用 hash 化的 JS bundle"
    )
    assert list((DIST_DIR / "assets").glob("*.js")), "web/dist/assets 下没有 JS"


def test_dist_bundle_is_vue_spa():
    """bundle 里应包含 Vue Router 的路由注册（管理后台前端路由存在）。"""
    js = "\n".join(f.read_text(encoding="utf-8") for f in (DIST_DIR / "assets").glob("*.js"))
    assert "/admin/login" in js, "bundle 缺少 /admin/login 路由（后台未打包？）"


def test_admin_routes_serve_spa():
    """FastAPI 把 /admin/* 都交给 SPA（不再有独立 admin HTML 页面）。"""
    from app.main import app
    with TestClient(app) as c:
        for path in ("/admin", "/admin/login", "/admin/accounts", "/admin/settings"):
            r = c.get(path)
            assert r.status_code == 200, f"{path} returned {r.status_code}"
            assert "<html" in r.text.lower()
            assert '<div id="app">' in r.text
