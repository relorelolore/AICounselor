# tests/conftest.py
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