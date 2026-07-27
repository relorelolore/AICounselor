# AI 辅导员 Agent

本地 RAG 驱动的学业辅导员：基于 LangChain + LangGraph + Chroma + bge-m3 + llama.cpp。

## 管理后台

启动服务后访问 `http://localhost:8000/admin`，使用默认账号 `admin / 147369` 登录。

⚠️ **首次登录后请立即修改默认密码**（`/admin/accounts` → 选中自己 → 改密）。

后台可做：
- 配置 AI 模型参数（LLM 推理 / 连接 / 检索 / 路径 / Embedding）
- 触发向量数据库重建索引（前台聊天界面的「重建索引」按钮已迁移至此）
- 管理多个管理员账号，支持 6 次错误后永久锁定 + 解锁

详细规范见 `docs/superpowers/specs/2026-07-25-admin-backend-design.md`。

### CSRF / 跨域访问

后台所有 mutating 端点（POST/PATCH/PUT/DELETE）都会校验 `Origin` 头，GET 豁免。默认行为：
- 允许 `COUNSELOR_ALLOWED_ORIGIN` 环境变量指向的源（默认 `http://localhost:8000`）
- **或** 允许 `Origin` 的 host:port 等于请求 `Host` 头（浏览器同源请求天然满足）

所以浏览器通过 `http://localhost:8000` / `http://127.0.0.1:8000` / `http://<LAN-IP>:8000` 任一地址访问都能正常工作。如需进一步收紧，把 `COUNSELOR_ALLOWED_ORIGIN` 设为唯一允许的源。

如果直接 `curl` 调后台 mutating 端点遇到 `403 origin not allowed`，给请求加上 `-H 'Origin: http://localhost:8000'`（匹配默认允许源）或加上 `-H "Host: <你的地址>"` 即可。

## 功能

- 在 `Documents/` 下放入 PDF/PPT/Word 文档
- 自动入索引（首启或点「重新入索引」）
- 单页 WebUI 提问，模型基于本地 llama.cpp 生成
- 多会话 UI：左侧栏管理多个会话，所有状态本地持久化（`localStorage`），后端无状态

## 准备

- Python 3.12+
- 运行中的 llama.cpp server：`http://localhost:8848/v1`
- `uv sync --extra dev` (deps already installed from Task 1; this is just a sanity check)
- **运行不需要 Node**：前端构建产物（`web/dist/`）已随仓库提交。仅前端开发需要 Node 20.19+ 与 pnpm（见「前端开发」）。

## 依赖

### 运行时要求

| 软件 | 版本 | 用途 |
|---|---|---|
| Python | 3.12+（`uv 0.11+` 管理虚拟环境） | 后端运行 |
| llama.cpp server | OpenAI 兼容端点 `http://localhost:8848/v1` | 本地 LLM 推理 |
| Node.js | 20.19+ | 仅前端开发/构建（运行服务不需要） |
| pnpm | 10+（推荐 11；构建脚本白名单见 `frontend/pnpm-workspace.yaml`） | 前端包管理 |

### Python 依赖（`pyproject.toml`）

| 包 | 版本约束 | 用途 |
|---|---|---|
| fastapi | >=0.110,<1.0 | Web 框架 |
| uvicorn[standard] | >=0.29.0 | ASGI 服务器 |
| websockets | >=12.0 | WS 聊天通道 |
| python-multipart | >=0.0.9 | 表单解析 |
| pydantic | >=2.6,<3.0 | 数据校验 |
| langchain | >=0.3,<1.0 | LLM 编排 |
| langchain-core | >=0.3,<1.0 | 消息/工具抽象 |
| langchain-community | >=0.3,<1.0 | 社区集成 |
| langchain-openai | >=0.2,<1.0 | OpenAI 兼容客户端（接 llama.cpp） |
| langchain-chroma | >=0.1.2 | Chroma 向量库集成 |
| langchain-huggingface | >=0.1.0 | bge-m3 embedding |
| langgraph | >=0.2,<1.0 | ReAct Agent 图 |
| langgraph-checkpoint-sqlite | >=2.0,<4.0 | 图状态持久化（历史遗留） |
| openai | >=1.40,<2.0 | OpenAI SDK |
| chromadb | >=0.5,<1.0 | 向量数据库 |
| sentence-transformers | >=3.0,<5.0 | bge-m3 模型运行时 |
| pypdf | >=5.0.0 | PDF 文档加载 |
| python-pptx | >=1.0.0 | PPTX 文档加载 |
| docx2txt | >=0.8 | DOCX 文档加载 |
| unstructured | >=0.14.0 | 文档解析辅助 |

开发依赖（`uv sync --extra dev`）：`pytest>=8.2`、`pytest-asyncio>=0.23`、`httpx>=0.27`、`anyio>=4.4`。

### 前端依赖（`frontend/package.json`）

| 包 | 版本约束 | 用途 |
|---|---|---|
| vue | ^3.5 | UI 框架 |
| vue-router | ^4.5 | SPA 路由（`/` 前台 + `/admin/*` 后台） |
| pinia | ^3.0 | 状态管理（chat / health / admin / theme） |
| naive-ui | ^2.43 | UI 组件库 |
| marked | ^16.0 | Markdown 渲染 |
| dompurify | ^3.2 | HTML 消毒（防 XSS） |

开发依赖：`vite ^7`（构建）、`@vitejs/plugin-vue ^6`、`typescript ~5.9`、`vue-tsc ^3`（类型检查）、`vitest ^3` + `jsdom ^26`（单测）。

## 启动

Linux / macOS：

```bash
bash scripts/run.sh
```

Windows（CMD）：

```bat
scripts\run.bat
```

两个脚本等价：`cd` 到仓库根、准备 `data/`、清理旧的 `checkpoints.db`、首启自动入索引、检查 `web/dist/index.html`、跑 `uv run uvicorn ... --reload`。`HOST` / `PORT` 环境变量可覆盖默认（`0.0.0.0` / `8000`）。

打开浏览器访问 `http://localhost:8000`。

## Web UI

前端是 **Vue 3 单页应用**（源码在 `frontend/`，构建产物在 `web/dist/`）：用户聊天前台（`/`）与管理后台（`/admin`）共用一个 SPA，由 Vue Router 切换。

打开后默认进入 **多会话 ChatGPT 风格**界面，所有状态保存在浏览器 `localStorage`（key 为 `counselor:state`），**后端不持久化任何对话**——重启服务器、刷新页面都不会丢失会话。

### 左侧栏（多会话管理）

- **＋ 新会话**：创建新对话，自动生成 UUID 标题。
- **点击会话项**：在右侧主区域切换并加载该会话的完整历史。
- **悬停会话项 → ⋯ → 重命名**：行内编辑会话标题（Enter 保存 / Esc 取消）。
- **⋯ → 删除**：删除该会话（会先弹确认）。
- **≡ 折叠按钮**：折叠侧边栏，最大化主区域（移动端默认收起，选会话后自动收起）。

每个会话项显示**自动标题**（取首条用户消息的前 24 字 + `…`）和**相对时间**（刚刚 / N 分钟前 / 昨天 / M/D），按「今天 / 昨天 / 本周 / 更早」分组。

### 主区域

- 空状态给出**示例问题卡片**，点击即发送。
- Markdown 渲染（marked + DOMPurify）：标题、列表、`code`、围栏代码块、表格、加粗/斜体、行内链接。
- **引用 chips**：模型回答末尾的 `📄 引 N` 小芯片，点击后从右侧滑出**参考资料抽屉**，展示该条引用对应的文档片段、文件名、页码。
- 流式响应中显示打字光标；回答归属会话 id，**生成中切换会话不会丢失**，切回可继续查看。
- 输入区字符计数（`0/4000`）、**发送** / **停止** 切换、Shift+Enter 换行 / Enter 发送。
- 顶栏支持**明/暗主题切换**（跟随系统 + 手动记忆）。
- 用户前台**不含**「重建索引」按钮（已迁移到管理后台 `/admin`）。

### 持久化

- 所有会话、消息、引用都在 `localStorage["counselor:state"]`。
- **会话 id**（UUID v4）只在 WebSocket 帧里作为审计字段携带，不参与任何服务端状态。
- 重启启动脚本（Linux：`bash scripts/run.sh` / `pkill -9 -f uvicorn`；Windows：`scripts\run.bat` / `taskkill /F /IM uvicorn.exe`）都不会丢失会话。
- 浏览器清缓存 / 隐私模式 → 会丢；想"重置"就在 ⋯ → 清空全部会话，或浏览器 DevTools 删除 `counselor:state`。

### 响应式

- 桌面：左栏 + 主区 + drawer 三栏，drawer 浮于主区右侧。
- 移动端（< 768px）：侧边栏默认收起（overlay 展开），drawer 全屏覆盖，主区占满。

## 前端开发

```bash
cd frontend
pnpm install        # 首次
pnpm dev            # 开发服务器 http://localhost:5173（/api、/ws 已代理到 :8000）
pnpm build          # 构建到 ../web/dist（提交仓库，供 run.sh 直接服务）
pnpm test           # vitest 单测（chat store / 工具函数）
pnpm typecheck      # vue-tsc 类型检查
```

改了前端代码后需要 `pnpm build` 并提交 `web/dist/`，否则 `run.sh` 服务的仍是旧产物。

## 测试

后端（offline 模式，无需 llama.cpp）：

```bash
OFFLINE=1 uv run --extra dev pytest -q
```

前端（chat store / 工具函数单测）：

```bash
cd frontend && pnpm test
```

`tests/test_llm.py::test_live_invoke` 默认 skip；启用：

```bash
SKIP_LIVE_LLM=0 uv run --extra dev pytest tests/test_llm.py -v
```

## 故障恢复

如果遇到 `agent error: ...` 错误（特别是某些浏览器特有），通常是浏览器侧 `localStorage` 状态损坏。修复：

```bash
# 浏览器 DevTools → Application → Storage → Clear site data
# 或者在 ⋯ 菜单点「清空全部会话」
# 不需要重启后端；后端无状态
```

如果 Chroma 索引损坏（`/api/health` 返回 `degraded` 或检索异常）：

```bash
# Linux / macOS
pkill -9 -f uvicorn
rm -rf data/
bash scripts/run.sh   # 自动重建索引 + chroma
```

```bat
REM Windows（PowerShell / CMD）
taskkill /F /IM uvicorn.exe
rmdir /s /q data
scripts\run.bat       :: 自动重建索引 + chroma
```

> **关于 `data/checkpoints.db`**：旧版 SqliteSaver 留下的检查点文件在 `scripts/run.sh` / `scripts/run.bat` 启动时会自动删除（启动脚本里的一次性迁移，幂等）。如果手动 `rm -rf data/`，该文件也会随 Chroma 索引一并清掉，无需单独处理。

如果后台登录/操作时遇到 `403 origin not allowed`：
- 浏览器访问：通过 `http://localhost:8000` / `127.0.0.1` / LAN IP 都默认允许（Origin host:port == 请求 Host）。
- curl 调 mutating 端点：加 `-H 'Origin: http://localhost:8000'`。
- 进一步收紧：设置 `COUNSELOR_ALLOWED_ORIGIN` 为唯一允许源，重启服务。

管理后台默认账号 `admin / 147369`，**首次登录后必须改密**；如忘记密码，删除 `data/admin.db` 后重启服务（会重新种子默认账号；其他账号需在首次登录后立即创建）。

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
| `COUNSELOR_ALLOWED_ORIGIN` | `http://localhost:8000`（管理后台 CSRF 允许源；默认还接受与请求 Host 匹配的 Origin） |
| `ADMIN_DB` | `./data/admin.db`（管理后台 SQLite 文件位置） |
| `WEB_DIR` | `./web/dist`（Vue SPA 构建产物目录，FastAPI 静态挂载到 `/`） |

注意：管理后台**部分参数（`temperature` / `max_tokens` / `k` / `chunk_size` 等）可在 `/admin/settings` 实时调整**，不需重启服务；其他（`base_url` / `model_name` / `timeout` / 路径 / Embedding 模型）需重启进程生效。

## 目录结构

见 `docs/superpowers/specs/2026-07-24-ai-counselor-design.md` §2.2。管理后台模块：
- `app/admin/` — 路由 + 业务逻辑（auth / accounts / settings / reindex / routes / schemas）
- `storage/admin_db.py` — SQLite 持久化
- `frontend/` — Vue 3 SPA 源码（Vite + Naive UI + Pinia + Vue Router；`src/views/` 用户前台，`src/views/admin/` 管理后台）
- `web/dist/` — 前端构建产物（已提交仓库，FastAPI 直接挂载）
