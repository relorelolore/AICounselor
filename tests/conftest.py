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
