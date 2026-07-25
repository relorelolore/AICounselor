# tests/conftest.py
import os
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


import pytest


@pytest.fixture(autouse=True)
def _reset_llm_config():
    """Reload llm.config before each test so module-level env-derived constants
    start from a clean baseline. Tests that mutate env vars still reload explicitly
    to observe the overridden values."""
    import importlib
    import llm.config as cfg
    importlib.reload(cfg)
    yield


@pytest.fixture(autouse=True)
def _maybe_skip_embedding_tests(request):
    """Skip tests that perform real embedding work when OFFLINE=1."""
    if os.environ.get("OFFLINE") == "1":
        if "chroma_roundtrip" in request.node.name.lower():
            pytest.skip("OFFLINE=1: skipping real embedding test")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Per-test FastAPI TestClient pointed at a tmp DATA_DIR.

    Reloads embedding/retriever/LLM/app singletons so env mutations are
    observed and the app rebuilds itself with the tmp DATA_DIR.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "Documents"))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setenv("OFFLINE", "1")
    import importlib
    import rag.embeddings as emb_mod
    importlib.reload(emb_mod)
    import rag.retriever as ret_mod
    importlib.reload(ret_mod)
    import llm.client as llm_client_mod
    importlib.reload(llm_client_mod)
    import app.main as app_main_mod
    importlib.reload(app_main_mod)
    from fastapi.testclient import TestClient
    return TestClient(app_main_mod.app)
