# llm/config.py
import os

LLAMACPP_BASE_URL: str = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8848/v1")
MODEL_NAME: str = os.environ.get("MODEL_NAME", "g0chu-Qwen3.6-35B-A3B-NVFP4")
DEFAULT_TEMPERATURE: float = float(os.environ.get("TEMPERATURE", "0.3"))
DEFAULT_MAX_TOKENS: int = int(os.environ.get("MAX_TOKENS", "2048"))