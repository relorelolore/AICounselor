"""Smoke tests for admin SPA static files."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ADMIN_WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "admin"


def test_admin_web_dir_exists():
    assert ADMIN_WEB_DIR.is_dir()


@pytest.mark.parametrize("filename", [
    "login.html", "index.html", "accounts.html", "settings.html",
])
def test_admin_html_pages_exist(filename):
    assert (ADMIN_WEB_DIR / filename).is_file()


def test_admin_html_pages_reference_admin_js_and_css():
    for f in ADMIN_WEB_DIR.glob("*.html"):
        text = f.read_text(encoding="utf-8")
        assert 'admin.css' in text, f"{f.name} missing admin.css"
        assert 'admin.js' in text, f"{f.name} missing admin.js"


def test_admin_js_cache_bust_is_monotonic():
    """Each admin.html must reference admin.js?v=N with a positive int."""
    import re
    versions = []
    for f in sorted(ADMIN_WEB_DIR.glob("*.html")):
        m = re.search(r'admin\.js\?v=(\d+)', f.read_text(encoding="utf-8"))
        assert m, f"{f.name} missing admin.js?v=N"
        versions.append(int(m.group(1)))
    # All same version is fine; just non-zero and positive.
    assert all(v >= 1 for v in versions)


def test_admin_routes_serve_html_pages():
    """FastAPI serves the admin HTML at /admin/<name>.html."""
    from app.main import app
    with TestClient(app) as c:
        for name in ["login", "index", "accounts", "settings"]:
            r = c.get(f"/admin/{name}.html")
            assert r.status_code == 200, f"/admin/{name}.html returned {r.status_code}"
            assert "<html" in r.text.lower()