# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目

本地 RAG 学业辅导员：LangChain + LangGraph + Chroma + bge-m3 + llama.cpp + FastAPI + Vue 3 SPA（WebSocket 聊天）。学生问题 → 由 LLM 决定是否调用 `search_documents` 工具 → ReAct Agent 整合工具结果 → WS 回答 + 引用。

设计/计划文档：
- `docs/superpowers/specs/2026-07-24-ai-counselor-design.md` — 14 节规范 + v2 增补（ReAct 工具调用，§v2.1–v2.7）
- `docs/superpowers/plans/2026-07-24-ai-counselor.md` — 14 个任务，每个含完整代码

## 工具链

- **uv 0.11+** 管理 Python 3.12 虚拟环境（`.venv/` 已生成）。`pip install` / `python -m pytest` 直接调用都不会工作 — 必须 `uv run` 或在 `.venv` 内。
- **llama.cpp** 在 `http://localhost:8848/v1` 提供 OpenAI 兼容接口；模型 `g0chu-Qwen3.6-35B-A3B-NVFP4`。该服务**不支持 embeddings**（返回 501，需 `--embeddings` 重启才能用）。
- **前端是 Vue 3 SPA**（`frontend/`，Vite + TypeScript + Naive UI + Pinia + Vue Router）：`pnpm dev` 开发（proxy 到 :8000）、`pnpm build` 构建到 `web/dist/`（**产物提交仓库**，运行服务无需 Node）。前端自管多会话持久化（`localStorage["counselor:state"]`，v1 结构），后端无状态，所有历史通过 WS `history` 字段随请求发送。

## 命令

| 用途 | 命令 |
|---|---|
| 启动服务（首启自动入索引） | `bash scripts/run.sh` |
| 启动后台 + 验证 | `bash scripts/run.sh &` 然后 `curl http://localhost:8000/api/health` |
| 全量测试（offline） | `OFFLINE=1 uv run --extra dev pytest -q` |
| 单文件测试 | `OFFLINE=1 uv run --extra dev pytest tests/test_tools.py -v`（或 `tests/test_graph.py`） |
| 前端构建 | `cd frontend && pnpm build`（输出 `web/dist/`，需提交） |
| 前端单测 / 类型检查 | `cd frontend && pnpm test` / `pnpm typecheck` |
| 前端开发服务器 | `cd frontend && pnpm dev`（:5173，/api + /ws 代理到 :8000） |
| 真实 LLM 调用 | `SKIP_LIVE_LLM=0 OFFLINE=1 uv run --extra dev pytest tests/test_llm.py::test_live_invoke -v` |
| 入索引 CLI | `uv run --extra dev python -m ingest --force` |
| 安装/同步依赖 | `uv sync --extra dev` |
| 完全重置数据 | `rm -rf data/`（`data/` 已 gitignore） |

## 包结构（spec §2.2）

| 包 | 职责 |
|---|---|
| `app/` | FastAPI 入口；`main.py` 装配、`routes_*.py` 路由、`schemas.py` Pydantic 模型 |
| `app/admin/` | 管理后台路由（`routes.py`）+ 业务逻辑（`auth.py` / `accounts.py` / `settings.py` / `reindex.py`）+ Pydantic schemas |
| `agent/` | LangGraph ReAct Agent + 状态 + 工具；`graph.py` 装配（`create_react_agent` + `build_search_documents_tool`）、`tools.py` 工具工厂、`prompts.py` 系统提示 + `format_docs_as_text` |
| `rag/` | 文档加载（PDF/PPTX/DOCX）、中文感知切分、Chroma retriever、bge-m3 embeddings、citation 格式化 |
| `ingest/` | 索引构建器 + `python -m ingest` CLI |
| `llm/` | OpenAI 兼容客户端指向 llama.cpp |
| `storage/` | 路径常量（`paths.py`）+ SQLite admin 持久化（`admin_db.py` → `data/admin.db`） |
| `frontend/` | Vue 3 SPA 源码（Vite + TS + Naive UI + Pinia + Vue Router）；`src/views/ChatView.vue` + `src/components/chat/` 用户前台，`src/views/admin/` 管理后台，`src/stores/` Pinia（chat 持久化、health 轮询、admin 会话、theme） |
| `web/dist/` | 前端构建产物（**提交仓库**），FastAPI 经 `SpaStaticFiles` 挂载到 `/`（no-store + history fallback） |

`storage/paths.py` 是所有磁盘路径的单一来源；不要散落 hardcode。

## 管理后台（admin subsystem）

- 后台入口：`/admin/login`（**不在用户前台显示入口**；SPA history fallback 使直达可用）；默认账号 `admin / 147369`，首次登录后**必须**改密。
- 后端：`app/admin/` 包（auth / accounts / settings / reindex / routes / schemas）；SQLite 持久化在 `storage/admin_db.py` → 单文件 `data/admin.db`（WAL + `threading.RLock`）。
- 路由：`/api/admin/{login,logout,me,accounts,settings,reindex,reindex/last}`；session cookie `counselor_admin`（HttpOnly + SameSite=Lax + 24h 滑动续期）。
- CSRF：所有 mutating 方法（POST/PATCH/PUT/DELETE）拒绝缺失或与请求 Host 不匹配的 `Origin` 头（GET 豁免）。默认允许 `COUNSELOR_ALLOWED_ORIGIN`（默认 `http://localhost:8000`）**或** Origin 的 host:port 等于请求 `Host` 头（浏览器同源请求天然满足）。可通过 `COUNSELOR_ALLOWED_ORIGIN` 环境变量收紧到特定源。Vite dev 下 proxy 已把 Origin 改写为 `http://localhost:8000`（见 `frontend/vite.config.ts`）。
- 锁定策略：6 次错误后**永久**锁定，必须其他管理员手动解锁。
- 可调参数分两类：热生效（`llm.*` 全部 / `retrieval.*` 全部 — 包括 `base_url` / `model_name` / `timeout` / `k` / `chunk_*`，由 `get_llm()` / `get_retriever()` / `split()` 每次调用读单例 + startup hook 把 admin DB 覆盖应用到单例）和需重启（`paths.documents_dir` / `paths.data_dir` / `paths.chroma_collection` / `embedding.model` — chroma collection 不可 in-place 改名 + SentenceTransformer 启动时一次性加载）；`PUT /api/admin/settings` 返回的 `restart_required` 字段列出后者。
- 前端：`frontend/src/views/admin/`（Login / AdminLayout / Dashboard / Accounts / Settings），路由守卫调 `GET /api/admin/me` 判登录态，401 → `/admin/login?redirect=...`。
- 用户前台去掉了「重建索引」按钮（迁移至后台），`/api/ingest` 已删除（重建索引仅走 `POST /api/admin/reindex`）。
- `llm/config.py` / `rag/retriever.py` / `rag/splitter.py` 从运行时单例读配置；`app/main.py::_load_admin_settings_into_singletons()` 在 startup 时把 admin DB 覆盖应用到单例，保证配置在 `--reload` / 完全重启后不丢。

## 前端架构（`frontend/`）

- Vue 3 SPA（Vite + TypeScript + Naive UI + Pinia + Vue Router），构建产物 `web/dist/` 提交仓库，由 `app/static_no_store.py::SpaStaticFiles` 挂载（no-store + GET/HEAD 404 回退 `index.html` 的 history fallback）。
- 所有会话状态存在 `localStorage["counselor:state"]`，schema 见 spec §2（version 1，与旧原生 JS 前端完全兼容）；后端无状态，多轮历史由前端每次 WS 请求随 `history` 字段发送。
- `src/stores/chat.ts`：多会话 CRUD + 持久化 + 流式状态（流式归属 chatId，切换会话不丢）；`src/api/ws.ts`：WS 客户端（4 类事件 + 90s 超时）；`src/stores/health.ts`：30s 轮询 `/api/health`；`src/stores/theme.ts`：明/暗主题。
- ChatGPT 风格侧边栏：可折叠、分组（今天 / 昨天 / 本周 / 更早），支持新建 / 行内重命名 / 删除 / 清空全部会话（Naive UI dialog 确认）。
- Markdown：marked + DOMPurify（`src/utils/markdown.ts`），引用 chips → Naive Drawer 展示片段。
- 资源带 content-hash，不再需要手工 `?v=N` bump；改前端后 `pnpm build` 并提交 `web/dist/`。

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
- 当前基线：`OFFLINE=1 uv run --extra dev pytest` → **195 passed, 2 skipped**（live llama.cpp + bge-m3 roundtrip 各 1 个 skip），覆盖 RAG/agent 套件 + admin 套件（`test_admin_{db,auth,accounts,settings,reindex,routes}.py`）+ SPA 静态服务 smoke（`test_api.py` / `test_admin_static.py`，断言 `web/dist` 产物 + history fallback）。
- 前端单测：`cd frontend && pnpm test`（vitest + jsdom，18 个）→ `src/stores/chat.spec.ts`（localStorage v1 兼容、CRUD、FakeWebSocket 驱动的事件流）与 `src/utils/format.spec.ts`（标题/时间/分组）。
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
| 管理后台 CSRF（`app/admin/routes.py::_check_origin`） | Origin 缺失或不匹配 `_ALLOWED_ORIGIN`/请求 Host 头 → 403。默认也允许 Origin host:port == 请求 Host 头（浏览器同源天然满足）；访问 `127.0.0.1`/LAN IP 不会触发 403。收紧用 `COUNSELOR_ALLOWED_ORIGIN` 环境变量。 |
| `n-config-provider` 默认渲染包裹 div | Naive UI 的 `NConfigProvider` 非 abstract 时渲染 `<div class="n-config-provider">`（无高度），会截断子树 `height: 100%` 链条（聊天页/后台布局塌陷成内容高）。`App.vue` 已加 `abstract`，`base.css` 有 `#app > .n-config-provider` 兜底；`AdminLayout` 内容区另需 `min-height: calc(100vh - 56px)`（n-layout-content 不自动撑满）。 |
| marked 输出 + `white-space: pre-wrap` | marked 生成的 HTML 标签之间带 `\n`，若容器 `pre-wrap` 会把这些换行渲染成多余空行（列表项间距暴增）。`pre-wrap` 只用于纯文本（用户消息/流式打字），`.md-body` 必须 `white-space: normal`；松散列表还要 `.md-body li > p { margin: 0 }`。 |
| pnpm 11 构建脚本白名单 | `package.json` 的 `pnpm.onlyBuiltDependencies` 在 pnpm 11 失效（esbuild postinstall 被拦 → vite 起不来）。必须写 `frontend/pnpm-workspace.yaml` 的 `allowBuilds: { esbuild: true }`（旧键名保留兼容 pnpm ≤10）。 |
| Node ≥22 自带 `localStorage` | Node 26 全局 `localStorage`（未配 `--localstorage-file` 时恒 undefined）会遮蔽 vitest jsdom 环境的实现（populateGlobal 跳过已存在于 global 的键）。`src/test-setup.ts` 用内存 Storage 显式替换。 |
| SPA fallback 抓不到 404 | `StaticFiles` 抛的是 **starlette** 的 `HTTPException`，catch `fastapi.HTTPException`（子类）抓不到 → `/admin` 直达 404。`app/static_no_store.py` 必须 catch `starlette.exceptions.HTTPException`。 |

## 环境变量（`llm/config.py` + `storage/paths.py` + 各模块）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLAMACPP_BASE_URL` | `http://localhost:8848/v1` | llama.cpp OpenAI 兼容端点 |
| `LLAMACPP_API_KEY` | `llama.cpp` | llama.cpp OpenAI 兼容端点 API key（默认 `"llama.cpp"`；切换到需鉴权的云服务时覆盖） |
| `MODEL_NAME` | `g0chu-Qwen3.6-35B-A3B-NVFP4` | 模型 id |
| `EMBED_MODEL` | `BAAI/bge-m3` | sentence-transformers |
| `DOCUMENTS_DIR` | `./Documents` | 入索引源 |
| `DATA_DIR` | `./data` | chroma + index_meta.json |
| `WEB_DIR` | `./web/dist` | Vue SPA 构建产物（挂载到 `/`） |
| `CHROMA_COLLECTION` | `counselor` | Chroma collection 名 |
| `OFFLINE` | `0` | `1` 跳过 bge-m3 下载（用于测试） |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` / `RETRIEVE_K` | 500 / 80 / 6 | splitter + retriever 参数 |
| `COUNSELOR_ALLOWED_ORIGIN` | `http://localhost:8000` | 管理后台 CSRF 允许的 Origin；默认还接受与请求 Host 匹配的 Origin（覆盖 `127.0.0.1`/LAN 访问） |
| `ADMIN_DB` | `./data/admin.db` | 管理后台 SQLite 文件位置（环境变量可覆盖） |

## WebSocket 协议（`app/routes_chat.py` + `frontend/src/api/ws.ts`）

4 类事件：`token`（assistant 消息内容，整段）、`citation`（`[{filename, page, snippet}]` 列表）、`done`（`{finish_reason: "stop"}`；v2 起不再有 `"no_doc"` 分支 — ReAct 由 LLM 决定是否调工具，chat route 落到 `ToolMessage` 即可拿到 citations）、`error`（`{data: "..."}`）。

前端 `src/stores/chat.ts` 用 `localStorage["counselor:state"]` 存所有会话；`session_id = chat.id`，同一会话多次发送沿用同一 id（仅作审计 hook，不参与图运行）。后端是无状态的；多轮历史由前端在每次请求时通过 `history` 字段随 WS 一起发送，LangGraph 用 `InMemorySaver` 或无 checkpointer 跑这一轮。

## 不属于本项目

- 多 Agent / Web 搜索工具 / 其他角色（spec §1.2 明确排除）
- 用户体系、鉴权、远程托管（单进程本地服务）
- Word/PPT 高保真还原（仅取文本）