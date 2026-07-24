# tests/test_ws.py
import json
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "Documents"))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setenv("OFFLINE", "1")
    import importlib
    import rag.embeddings as emb_mod; importlib.reload(emb_mod)
    import rag.retriever as ret_mod; importlib.reload(ret_mod)
    import llm.client as llm_client_mod; importlib.reload(llm_client_mod)
    import app.main as app_main_mod; importlib.reload(app_main_mod)
    return TestClient(app_main_mod.app)


def test_ws_validation_rejects_long_message(client):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text(json.dumps({"session_id": "550e8400-e29b-41d4-a716-446655440000",
                                 "message": "x" * 5000}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data["event"] == "error"


def test_ws_validation_rejects_bad_uuid(client):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text(json.dumps({"session_id": "not-a-uuid", "message": "hi"}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data["event"] == "error"