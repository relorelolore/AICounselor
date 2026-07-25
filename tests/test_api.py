# tests/test_api.py
import os
import tempfile
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "Documents"))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setenv("OFFLINE", "1")
    # 重置 singleton
    import importlib
    import rag.embeddings as emb_mod
    importlib.reload(emb_mod)
    import rag.retriever as ret_mod
    importlib.reload(ret_mod)
    import llm.client as llm_client_mod
    importlib.reload(llm_client_mod)
    import app.main as app_main_mod
    importlib.reload(app_main_mod)
    return TestClient(app_main_mod.app)


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
    assert 'statusText.textContent = "连接超时"' in app_js


def test_frontend_script_is_cache_busted(client):
    index_html = client.get("/").text
    assert '<script src="app.js?v=3"></script>' in index_html
