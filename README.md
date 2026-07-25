# AI 辅导员 Agent

本地 RAG 驱动的学业辅导员：基于 LangChain + LangGraph + Chroma + bge-m3 + llama.cpp。

## 功能

- 在 `Documents/` 下放入 PDF/PPT/Word 文档
- 自动入索引（首启或点「重新入索引」）
- 单页 WebUI 提问，模型基于本地 llama.cpp 生成
- 多轮会话持久化

## 准备

- Python 3.11+
- 运行中的 llama.cpp server：`http://localhost:8848/v1`
- `uv sync --extra dev` (deps already installed from Task 1; this is just a sanity check)

## 启动

```bash
bash scripts/run.sh
```

打开浏览器访问 `http://localhost:8000`。

## 测试

```bash
pytest -q
```

`tests/test_llm.py::test_live_invoke` 默认 skip；启用：

```bash
SKIP_LIVE_LLM=0 pytest tests/test_llm.py -v
```

## 故障恢复

如果遇到 `agent error: ...` 错误（特别是某些浏览器特有），多半是 LangGraph checkpointer 状态损坏。修复：

```bash
pkill -9 -f uvicorn
rm -rf data/
bash scripts/run.sh   # 自动重建索引 + chroma
```

## 配置（环境变量）

| 变量 | 默认值 |
|---|---|
| `LLAMACPP_BASE_URL` | `http://localhost:8848/v1` |
| `MODEL_NAME` | `g0chu-Qwen3.6-35B-A3B-NVFP4` |
| `EMBED_MODEL` | `BAAI/bge-m3` |
| `DOCUMENTS_DIR` | `./Documents` |
| `DATA_DIR` | `./data` |
| `OFFLINE` | `0`（设为 `1` 跳过 embedding 下载） |
| `CHUNK_SIZE` | `500` |
| `CHUNK_OVERLAP` | `80` |
| `RETRIEVE_K` | `6` |

## 目录结构

见 `docs/superpowers/specs/2026-07-24-ai-counselor-design.md` §2.2。
