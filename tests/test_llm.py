# tests/test_llm.py
import os
import pytest
from langchain_core.messages import HumanMessage


def test_default_base_url(monkeypatch):
    monkeypatch.delenv("LLAMACPP_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    # 重新导入以触发 defaults
    import importlib, llm.config as cfg
    importlib.reload(cfg)
    assert cfg.LLAMACPP_BASE_URL == "http://localhost:8848/v1"
    assert cfg.MODEL_NAME == "g0chu-Qwen3.6-35B-A3B-NVFP4"


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLAMACPP_BASE_URL", "http://h:1/v1")
    monkeypatch.setenv("MODEL_NAME", "m")
    import importlib, llm.config as cfg
    importlib.reload(cfg)
    assert cfg.LLAMACPP_BASE_URL == "http://h:1/v1"
    assert cfg.MODEL_NAME == "m"


def test_get_llm_uses_openai_compat(monkeypatch):
    """get_llm 必须基于 ChatOpenAI 指向 OpenAI-compatible base url。"""
    from langchain_openai import ChatOpenAI
    from llm.client import get_llm
    llm = get_llm(streaming=False, temperature=0.0)
    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == "http://localhost:8848/v1"
    assert llm.model_name == "g0chu-Qwen3.6-35B-A3B-NVFP4"
    assert llm.streaming is False
    assert llm.temperature == 0.0


@pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_LLM", "1") == "1",
    reason="live llama.cpp call skipped by default",
)
def test_live_invoke(monkeypatch):
    """实际打 llama.cpp。运行：SKIP_LIVE_LLM=0 pytest tests/test_llm.py::test_live_invoke"""
    from llm.client import get_llm
    llm = get_llm(streaming=False, temperature=0.0)
    out = llm.invoke([HumanMessage(content="只回答 OK：1+1=?")])
    assert "2" in out.content or "OK" in out.content