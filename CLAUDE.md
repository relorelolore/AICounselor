# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目

本地 RAG 学业辅导员：LangChain + LangGraph + Chroma + bge-m3 + llama.cpp + FastAPI + 原生 HTML WebSocket 前端。学生问题 → 由 LLM 决定是否调用 `search_documents` 工具 → ReAct Agent 整合工具结果 → 流式 WS 回答 + 引用。

设计/计划文档：
- `docs/superpowers/specs/2026-07-24-ai-counselor-design.md` — 14 节规范 + v2 增补（ReAct 工具调用，§v2.1–v2.7）
- `docs/superpowers/plans/2026-07-24-ai-counselor.md` — 14 个任务，每个含完整代码

## 工具链

- **uv 0.11+** 管理 Python 3.12 虚拟环境（`.venv/` 已生成）。`pip install` / `python -m pytest` 直接调用都不会工作 — 必须 `uv run` 或在 `.venv` 内。
- **llama.cpp** 在 `http://localhost:8848/v1` 提供 OpenAI 兼容接口；模型 `g0chu-Qwen3.6-35B-A3B-NVFP4`。该服务**不支持 embeddings**（返回 501，需 `--embeddings` 重启才能用）。
- **Web/不提供 npm 构建**，纯原生 JS。

## 命令

| 用途 | 命令 |
|---|---|
| 启动服务（首启自动入索引） | `bash scripts/run.sh` |
| 启动后台 + 验证 | `bash scripts/run.sh &` 然后 `curl http://localhost:8000/api/health` |
| 全量测试（offline） | `OFFLINE=1 uv run --extra dev pytest -q` |
| 单文件测试 | `OFFLINE=1 uv run --extra dev pytest tests/test_tools.py -v`（或 `tests/test_graph.py`） |
| 真实 LLM 调用 | `SKIP_LIVE_LLM=0 OFFLINE=1 uv run --extra dev pytest tests/test_llm.py::test_live_invoke -v` |
| 入索引 CLI | `uv run --extra dev python -m ingest --force` |
| 安装/同步依赖 | `uv sync --extra dev` |
| 完全重置数据 | `rm -rf data/`（`data/` 已 gitignore） |

## 包结构（spec §2.2）

| 包 | 职责 |
|---|---|
| `app/` | FastAPI 入口；`main.py` 装配、`routes_*.py` 路由、`schemas.py` Pydantic 模型 |
| `agent/` | LangGraph ReAct Agent + 状态 + 工具；`graph.py` 装配（`create_react_agent` + `build_search_documents_tool`）、`tools.py` 工具工厂、`prompts.py` 系统提示 + `format_docs_as_text` |
| `rag/` | 文档加载（PDF/PPTX/DOCX）、中文感知切分、Chroma retriever、bge-m3 embeddings、citation 格式化 |
| `ingest/` | 索引构建器 + `python -m ingest` CLI |
| `llm/` | OpenAI 兼容客户端指向 llama.cpp |
| `storage/` | 路径常量（`paths.py`），所有磁盘位置经此模块 |
| `web/` | 原生 HTML+JS+CSS 单页 Chat UI |

`storage/paths.py` 是所有磁盘路径的单一来源；不要散落 hardcode。

## LangGraph Agent（`agent/graph.py`）

```
START ↔ agent (LLM) ↔ tools (search_documents) → END
```

- `agent/graph.py::build_graph` 用 `langgraph.prebuilt.create_react_agent` 装配 ReAct Agent；模型自带 `search_documents(query: str) -> str` 工具，**LLM 自己决定**是否调用（spec §v2.1 / §v2.2）。
- `agent/tools.py::build_search_documents_tool(retriever)` 工厂函数把任意 Chroma-like retriever 包成 LangChain `@tool(response_format="content_and_artifact")`；返回 `(text, docs)`，由 ToolNode 提升到 `ToolMessage.artifact` 字段，**chat route 据此生成 citations**（spec §v2.4）。
- `agent/prompts.py::COUNSELOR_SYSTEM_PROMPT` 温暖辅导员人设，引导模型「寒暄/历史/闲聊**不要**调用工具」。
- `agent/state.py`：`AgentState` 只剩 `messages`（ReAct 内部管理 `ToolMessage`）+ `citations`（由 chat route 在终态手工填充）。
- WebSocket 路由（`app/routes_chat.py`）用 `await graph.ainvoke(...)` 取终态，单次 `token` 事件发出**整段**答案（**非增量**流式，Task 12 fix）。后续 hardening：把 ReAct Agent 改用 `astream_events` 监控 `on_chat_model_stream` 拿增量 token（spec §v2.6）。
- 已知边界（spec §v2.6）：ReAct 可能多次推理，本地模型小概率不调或多调工具——通过工具 docstring 引导。

## 测试约定

- 全部测试在 `tests/`，**无 `__init__.py`**（pytest rootdir 自动发现）。
- `tests/conftest.py` 提供两个 autouse fixture：`_reset_llm_config`（每次前 `importlib.reload(llm.config)`）和 `_maybe_skip_embedding_tests`（`OFFLINE=1` 时跳过 `chroma_roundtrip` 测试，避免下载 bge-m3）。
- `tests/test_tools.py` 导出 `FakeRetriever`；`tests/test_graph.py` 内的 `RotatingFakeChat`（继承 `BaseChatModel`，`bind_tools` 返回 `self`）用于模拟 ReAct 多轮响应（脚本化的 `AIMessage`/`str` 序列，含 `tool_calls`）。两者配合即可完整驱动 ReAct 流程，无需 llama.cpp。
- 当前基线：`OFFLINE=1 uv run --extra dev pytest` → **39 passed, 2 skipped**（live llama.cpp + bge-m3 roundtrip），覆盖 `test_tools.py`（9 个）+ `test_graph.py`（3 个 ReAct 场景）= 12 个 Agent 单测。
- **不在** brief / fixture 文件夹下加 `tests/__init__.py`。
- **不要**用 `python -m pytest` / `pytest` — 必须 `uv run --extra dev pytest` 才能解析 `.venv/`。

## 已知陷阱（review 修复历史）

| 位置 | 行为 / 原因 |
|---|---|
| `ingest/fingerprint.py` 的 `IndexMeta` | `set()` / `set_failed()` **每次调用都写盘**（`__post_init__` 自动 load + 自动 save）。`ingest/indexer.py::_process_one` 故意不走 `meta.set()`，直接 `meta.files[path] = {...}`，最后 `meta.save()` 一次 — 否则 N 个文档会触发 N 次 disk write。 |
| `langchain-huggingface 0.3.1` | `HuggingFaceEmbeddings.__init__` **eager** 创建 `SentenceTransformer`，违反 brief「lazy init」声明。`tests/test_retriever.py::test_embeddings_lazy_init` 用 `FakeHuggingFaceEmbeddings` + monkey-patch + `cache_clear()` finally（Task 5 review 修复 cache pollution）。 |
| `chromadb 0.6.x` 集合名规则 | 3-63 字符，alphanumeric 起止，无 `..`。`tests/test_retriever.py` 用 `"test_collection"`（Task 5 review 修复 `"t"`）。 |
| `.gitignore` 的 `/main.py` | **根锚定**（Task 11 修复）— 否则会误屏蔽 `app/main.py`。`main.py` uv-init stub 在根目录被 gitignore。 |
| `langchain-community 0.3.x` | 每次 import 打 `DeprecationWarning: langchain-community is being sunset`。`pytest.ini` `filterwarnings` 只屏蔽 `DeprecationWarning`，**不**屏蔽 `PendingDeprecationWarning`，所以仍有提示 — 无害。 |
| `numpy 2.4.4` | lockfile 解析到 numpy 2.4.4（plan 没设上限）。langchain 0.3.x 已兼容；plan 代码不直接 import numpy。可考虑加 `numpy<2.0` 直接依赖。 |
| `LLAMACPP_BASE_URL` 不可达 | `/api/health` 返回 `degraded`（llm=False），不抛 5xx；WS handler 异常路径会 `error` 事件。 |

## 环境变量（`llm/config.py` + `storage/paths.py` + 各模块）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLAMACPP_BASE_URL` | `http://localhost:8848/v1` | llama.cpp OpenAI 兼容端点 |
| `MODEL_NAME` | `g0chu-Qwen3.6-35B-A3B-NVFP4` | 模型 id |
| `EMBED_MODEL` | `BAAI/bge-m3` | sentence-transformers |
| `DOCUMENTS_DIR` | `./Documents` | 入索引源 |
| `DATA_DIR` | `./data` | chroma + checkpoints.db + index_meta.json |
| `WEB_DIR` | `./web` | 静态前端 |
| `CHROMA_COLLECTION` | `counselor` | Chroma collection 名 |
| `OFFLINE` | `0` | `1` 跳过 bge-m3 下载（用于测试） |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` / `RETRIEVE_K` | 500 / 80 / 6 | splitter + retriever 参数 |

## WebSocket 协议（`app/routes_chat.py` + `web/app.js`）

4 类事件：`token`（assistant 消息内容，整段）、`citation`（`[{filename, page, snippet}]` 列表）、`done`（`{finish_reason: "stop"}`；v2 起不再有 `"no_doc"` 分支 — ReAct 由 LLM 决定是否调工具，chat route 落到 `ToolMessage` 即可拿到 citations）、`error`（`{data: "..."}`）。

前端 `web/app.js` 用 `localStorage.session_id`（UUID）做会话恢复；每个连接对应 LangGraph `thread_id`，多轮历史由 `SqliteSaver` 持久化到 `data/checkpoints.db`。

## 不属于本项目

- 多 Agent / Web 搜索工具 / 其他角色（spec §1.2 明确排除）
- 用户体系、鉴权、远程托管（单进程本地服务）
- Word/PPT 高保真还原（仅取文本）