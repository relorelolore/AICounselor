# llm/client.py
from langchain_openai import ChatOpenAI

from .config import get_llm_settings


def get_llm(*, streaming: bool = True) -> ChatOpenAI:
    s = get_llm_settings()
    return ChatOpenAI(
        base_url=s.base_url,
        api_key="not-needed",          # llama.cpp doesn't need a key
        model=s.model_name,
        streaming=streaming,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
        timeout=s.timeout,
    )