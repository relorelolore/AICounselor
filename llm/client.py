# llm/client.py
from langchain_openai import ChatOpenAI
from .config import (
    LLAMACPP_BASE_URL,
    MODEL_NAME,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
)


def get_llm(*, streaming: bool = True, temperature: float | None = None,
            max_tokens: int | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=LLAMACPP_BASE_URL,
        api_key="not-needed",          # llama.cpp 不需要 key
        model=MODEL_NAME,
        streaming=streaming,
        temperature=temperature if temperature is not None else DEFAULT_TEMPERATURE,
        max_tokens=max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS,
        timeout=120,
    )