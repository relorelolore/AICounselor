# AI Counselor — 管理后台设计 (Admin Backend)

> 把现有的单用户聊天系统拆分成两个独立的部分：
> **用户前台**（当前 `/` 路径下的聊天 SPA，行为基本不变）和
> **管理后台**（`/admin*` 下的 SPA + `/api/admin/*` JSON API，管理 AI 模型参数、触发索引重建、增删改查管理员账号）。

**单进程单端口 FastAPI**。所有 admin 数据走单一 SQLite 文件 `data/admin.db`，账号/会话/配置全部入库。

---

## §1. 架构总览

```
Browser ──┬── /                              ── web/index.html (用户聊天 SPA，行为不变)
          ├── /ws/chat                       ── WebSocket (现有 chat route)
          ├── /api/health                    ── 公共 (现有 health route)
          └── /admin/*                       ── web/admin/* 静态 SPA + /api/admin/* JSON API
                ├── /admin/login             (登录页，公共)
                ├── /admin                   (仪表盘，需登录)
                ├── /admin/accounts          (账号 CRUD，需登录)
                ├── /admin/settings          (参数配置，需登录)
                └── /api/admin/*             (JSON API，Session Cookie 鉴权)
```

- 单 FastAPI 进程，端口不变 (默认 8000)。
- 管理后台代码独立成 `app/admin/` 包，跟现有 `agent/`、`rag/`、`ingest/`、`llm/` 平级。
- 用户前台 SPA **不出现任何后台链接**；后台入口只能通过直接访问 `/admin/login` 到达。

---

## §2. 组件与文件结构

### 新增包 / 模块

| 文件 | 职责 |
|---|---|
| `app/admin/__init__.py` | 包标识 |
| `app/admin/auth.py` | 密码 hash/verify、session 生命周期、`login_attempt()` 主流程 |
| `app/admin/accounts.py` | 账号 CRUD + 锁定/解锁 + 自我保护规则 |
| `app/admin/settings.py` | LLM / Retrieval / Paths / Embedding 配置读写 + 热生效 |
| `app/admin/reindex.py` | 包装 `ingest.indexer.build_index`，写 last_reindex 到 kv 表 |
| `app/admin/routes.py` | FastAPI router（所有 `/api/admin/*` 端点） |
| `app/admin/schemas.py` | Pydantic 模型 |
| `storage/admin_db.py` | SQLite 连接 + 表结构 + 所有 admin 数据的 CRUD 函数 |
| `web/admin/login.html` | 登录页 |
| `web/admin/index.html` | 仪表盘（重建索引） |
| `web/admin/accounts.html` | 账号管理表 |
| `web/admin/settings.html` | 参数配置表单 |
| `web/admin/admin.css` | 后台共享样式 |
| `web/admin/admin.js` | 后台共享脚本 (requireSession 守卫、toast、fetch 包装) |
| `tests/test_admin_db.py` | SQLite 持久化测试 |
| `tests/test_admin_auth.py` | 密码 & 会话测试 |
| `tests/test_admin_accounts.py` | 账号 CRUD + 锁定测试 |
| `tests/test_admin_settings.py` | 配置 CRUD + 热生效测试 |
| `tests/test_admin_routes.py` | FastAPI 路由集成测试 |
| `tests/test_admin_static.py` | 后台 SPA 静态文件 smoke 测试 |

### 修改文件

| 文件 | 变更 |
|---|---|
| `app/main.py` | 引入 `app.admin.routes.router`；mount `/admin` → `web/admin/`；保留 `NoStoreStaticFiles` 保证无缓存 |
| `app/routes_ingest.py` | **删除** — ingest 改由 `/api/admin/reindex` 独享 |
| `web/index.html` | 删除 `<button id="reindex">` |
| `web/app.js` | 删除 `reindexBtn.addEventListener(...)` 块 (~13 行) |
| `storage/paths.py` | 加 `ADMIN_DB` 和 `ADMIN_WEB_DIR` |
| `llm/config.py` | 改造为可热替换的 `LLMConfig` 单例 + 访问器 |
| `llm/client.py` | `get_llm()` 每次调用从单例读 settings |
| `rag/retriever.py` | `get_retriever()` / `collection_count()` 每次从 settings 单例读 `k` |
| `rag/splitter.py` | `split()` 每次从 settings 单例读 `chunk_size` / `chunk_overlap` |
| `tests/test_api.py` | 新增断言：`web/index.html` 不含 `id="reindex"`、`/api/ingest` 返回 404 |
| `tests/conftest.py` | 加 `_reset_admin_state` autouse fixture + `admin_db` / `admin_client` / `logged_in_admin` fixtures |
| `CLAUDE.md` | 加 管理后台 子节；更新包结构表；记默认账号 |
| `README.md` | 加 管理后台 子节 |

### 删除 / 移除

- 整个 `app/routes_ingest.py` 文件
- `web/index.html` 中的 `id="reindex"` 按钮
- `web/app.js` 中的 reindex click handler
- 原计划中的 `data/admin/{accounts,sessions,settings,last_reindex}.json` — 由单一 `data/admin.db` 取代

---

## §3. 持久化层 — `storage/admin_db.py`

### 单一 SQLite 文件
- 路径：`data/admin.db`（环境变量 `DATA_DIR` 可覆盖根目录）
- Python 标准库 `sqlite3`，不引入新依赖
- 模块启动时懒初始化连接 + 建表

### 连接策略
- 模块级单例 `_conn: sqlite3.Connection`
- `check_same_thread=False` + `PRAGMA journal_mode=WAL`
- 一个 `threading.RLock` (`_WRITE_LOCK`) 串行化所有写操作
- 读操作在 WAL 下天然并发
- 提供 `reset_for_tests()` 函数在测试时丢弃连接、删除文件、重新建表

### 表结构

```sql
CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  id              TEXT PRIMARY KEY,
  username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash   TEXT NOT NULL,
  salt            TEXT NOT NULL,
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  locked          INTEGER NOT NULL DEFAULT 0,    -- 0 / 1
  created_at      REAL NOT NULL,                 -- unix epoch seconds
  updated_at      REAL NOT NULL,
  last_login_at   REAL
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id   TEXT PRIMARY KEY,
  account_id   TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at   REAL NOT NULL,
  expires_at   REAL NOT NULL,
  last_seen_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS settings (
  section     TEXT PRIMARY KEY,             -- 'llm' | 'retrieval' | 'paths' | 'embedding'
  data        TEXT NOT NULL,                -- JSON 序列化的 section 字段
  updated_at  REAL NOT NULL,
  updated_by  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,                       -- 'startup_time' | 'last_reindex'
  v TEXT NOT NULL                           -- JSON-encoded value
);
```

### 公开 API

```python
# accounts 子命名空间
list_accounts() -> list[dict]                          # 返回字段不含 password_hash/salt
get_account_by_username(username) -> dict | None
get_account_by_id(account_id) -> dict | None
create_account(username, password_hash, salt) -> dict
update_account(account_id, **fields) -> dict
delete_account(account_id) -> None
increment_failed_attempts(account_id) -> int          # 返回新计数值
reset_failed_attempts(account_id) -> None
set_locked(account_id, locked: bool) -> None

# sessions 子命名空间
create_session(account_id) -> str                      # 返回 session_id
get_session(session_id) -> dict | None                 # 过期或缺失返回 None
touch_session(session_id) -> None                      # 滑动续期
delete_session(session_id) -> None
cleanup_expired_sessions() -> int                      # 惰性清理，返回删除数

# settings 子命名空间
get_setting(section) -> dict | None                    # 反序列化 JSON；缺失返回 None
get_all_settings() -> dict                             # {section: dict}
set_setting(section, data: dict, updated_by: str) -> None

# kv 子命名空间
get_kv(key) -> dict | None
set_kv(key, value: dict) -> None
```

### 默认账号种子
- 连接建立后执行 `SELECT COUNT(*) FROM accounts`
- 若返回 0 → INSERT 一行：`username='admin'`, `password_hash=hash('147369', 新盐)`, `failed_attempts=0`, `locked=0`
- 同时 stderr 输出：
  ```
  [admin] seeded default admin account (username=admin); change password on first login
  [admin] admin login: http://localhost:8000/admin/login
  ```
- 每次应用启动时调用 `set_kv('startup_time', {'ts': time.time()})`

### 损坏处理
- 连接时遇到 `sqlite3.DatabaseError`：把 `data/admin.db` 重命名为 `data/admin.db.broken-{timestamp}`，重新建表 + 重新种子默认账号
- WAL 模式下崩溃恢复是自动的，不需手工干预
- `PermissionError` / `disk full` 直接 500（管理员本来就需要文件系统权限）

---

## §4. 认证流、锁定、Session

### 登录流程

```
POST /api/admin/login {username, password}
  ↓
auth.login_attempt(username, password)
  ├── 账号不存在 → 401 "invalid credentials"（与错误密码同消息，避免枚举）
  ├── account.locked == 1 → 423 "account locked"
  ├── 密码正确 → reset_failed_attempts()；create_session()；返回 Set-Cookie
  └── 密码错误 → increment_failed_attempts()
        ├── 若新计数 == 6 → set_locked(True)；返回 423 "account locked (too many failed attempts)"
        └── 否则         → 401 "invalid credentials"
```

- `failed_attempts` 计数跨重启持久化（SQLite 落盘）
- 计数只在「成功登录」之后才 reset
- 锁定是**永久的**（`locked=1`），必须由其他管理员手动解锁

### Session Cookie

- Cookie 名：`counselor_admin`
- 值：`secrets.token_urlsafe(32)`
- 属性：`HttpOnly; SameSite=Lax; Path=/`（不上 `Secure` 因为本地 HTTP；README 标注生产硬化建议）
- 有效期：24 小时，每次成功鉴权滑动续期 24 小时（`touch_session()`）
- 过期会话惰性清理：`get_session()` 时若发现 `expires_at < now` 即删除并返回 None

### 退出登录

`POST /api/admin/logout` → `delete_session(session_id)` + 清除 Cookie。

### 自我保护规则

| 操作 | 规则 |
|---|---|
| `DELETE /accounts/{id}` 且 `id == 当前账号` | 400 "cannot delete your own account" |
| `DELETE /accounts/{id}` 且将留下 0 个管理员 | 400 "cannot delete the last admin account" |
| `PATCH /accounts/{id}`（改密）为自己 | 必须带 `old_password`，验证后才生效 |
| `PATCH /accounts/{id}`（改密）为他人 | 无需 `old_password` |
| `PATCH /accounts/{id}` `{unlock: true}` 给自己 | 400 "cannot self-unlock; ask another admin" |
| `unlock` 动作同时自动 `reset_failed_attempts(0)` | 是 |

### `require_session` 依赖

```python
async def require_session(request: Request) -> dict:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if not sid: raise HTTPException(401, "unauthenticated")
    sess = admin_db.get_session(sid)
    if sess is None: raise HTTPException(401, "session expired")
    admin_db.touch_session(sid)
    request.state.account = admin_db.get_account_by_id(sess["account_id"])
    return sess
```

每个受保护端点声明 `Depends(require_session)`。

### 鉴权范围

| 路径 | 鉴权要求 |
|---|---|
| `/`、`/ws/chat`、`/api/health` | 公共（不变） |
| `/admin/login`（页面 + `POST /api/admin/login`） | 公共 |
| 其他 `/api/admin/*`、`/admin` (页面) | 必须有有效 Session |

`/api/ingest` 整体删除，不再有公共 reindex。

---

## §5. Admin 路由表 (`app/admin/routes.py`)

所有非 `/login` 端点都 `Depends(require_session)`。

| Method | Path | 请求体 / 动作 |
|---|---|---|
| POST | `/login` | `{username, password}` → Set-Cookie + 返回用户信息 |
| POST | `/logout` | 清除 Session + Cookie |
| GET | `/me` | 返回 `{username, created_at}` 等当前账号信息 |
| GET | `/accounts` | 列出所有账号（不含 hash/salt） |
| POST | `/accounts` | 新建 `{username, password}` |
| PATCH | `/accounts/{id}` | 更新（密码/unlock/重命名） |
| DELETE | `/accounts/{id}` | 删除 |
| GET | `/settings` | 读取全部生效配置（4 个 section） |
| PUT | `/settings` | 更新一个或多个 section |
| POST | `/reindex` | body `{force?: bool}`，触发 `build_index(force=…)` |

### Pydantic schemas (`app/admin/schemas.py`)

- `LoginRequest(username, password)`
- `LoginResponse(username, created_at)`
- `MeResponse(username, created_at, last_login_at)`
- `AccountPublic(id, username, created_at, updated_at, last_login_at, failed_attempts, locked)`
- `AccountCreate(username, password)` —— 验证用户名 3-32 字符 `[a-z0-9_-]+`、密码 ≥ 6 字符
- `AccountUpdate(...)` —— 用 `model_config = ConfigDict(extra='forbid')`；字段都可空，`old_password` 仅在改自己密码时校验
- `LLMSettings(base_url, model_name, temperature, max_tokens, timeout, top_p, frequency_penalty, presence_penalty)`
- `RetrievalSettings(k, chunk_size, chunk_overlap)`
- `PathsSettings(documents_dir, data_dir, chroma_collection)`
- `EmbeddingSettings(model)`
- `SettingsPatch(sections: dict[str, dict])` —— `sections["llm"] = {...}` 仅校验提供的 section
- `ReindexRequest(force: bool = False)`
- `ReindexResult` —— 复用现有 `app/schemas.py::IndexResult`

### 字段范围校验

| 字段 | 类型 | 范围 / 约束 |
|---|---|---|
| `temperature` | float | 0.0 ≤ x ≤ 2.0 |
| `max_tokens` | int | 1 ≤ x ≤ 32768 |
| `top_p` | float | 0.0 ≤ x ≤ 1.0 |
| `frequency_penalty` | float | -2.0 ≤ x ≤ 2.0 |
| `presence_penalty` | float | -2.0 ≤ x ≤ 2.0 |
| `timeout` | int | 5 ≤ x ≤ 600（秒） |
| `k` | int | 1 ≤ x ≤ 50 |
| `chunk_size` | int | 50 ≤ x ≤ 5000 |
| `chunk_overlap` | int | 0 ≤ x < chunk_size |

校验失败返回 400 + 字段级错误信息。

### 修改现有代码的具体清单

1. **删除 `app/routes_ingest.py`**
2. **修改 `app/main.py`**：
   - 引入 `from .admin.routes import router as admin_router`
   - 引入 `from .admin.schemas import ...`（如需导出 OpenAPI）
   - `app.include_router(admin_router, prefix="/api/admin")`
   - 把 `app.mount("/", NoStoreStaticFiles(...))` 之前的 root mount 改成保留；
     加 `app.mount("/admin", NoStoreStaticFiles(directory=ADMIN_WEB_DIR, html=True), name="admin-web")`
3. **修改 `web/index.html`**：删除 line 27 的 `<button id="reindex" ...>重建索引</button>`
4. **修改 `web/app.js`**：删除 line 582-594 的 `reindexBtn.addEventListener(...)` 块（含 `try/finally`）
5. **修改 `storage/paths.py`**：
   ```python
   ADMIN_DB: str = os.environ.get("ADMIN_DB", os.path.join(DATA_DIR, "admin.db"))
   ADMIN_WEB_DIR: str = os.environ.get("ADMIN_WEB_DIR", "./web/admin")
   ```
6. **修改 `llm/config.py`**：把模块级常量改为 `LLMConfig` dataclass 单例 + `get_llm_settings()` / `update_llm_settings(partial)`
7. **修改 `llm/client.py`**：`get_llm()` 改为读 `get_llm_settings()` 单例
8. **修改 `rag/retriever.py`**：`get_retriever(k=None)` 默认值从 settings 取
9. **修改 `rag/splitter.py`**：`split(docs)` 内部读 settings 单例
10. **修改 `tests/test_api.py`**：加 reindex 按钮移除断言、`/api/ingest` 返回 404 断言

### `scripts/run.sh`

无需修改；首启动仍自动入索引。`data/admin.db` 第一次访问 `/api/admin/*` 时自动创建。

---

## §6. 管理后台 SPA — 页面与导航

纯 vanilla JS，无框架、无构建步骤。多 HTML 文件 + 共享 JS/CSS，模拟多页面 SPA。

### 文件清单 (`web/admin/`)

```
admin.css           # 后台所有页面共享样式
admin.js            # requireSession 守卫、toast、fetch 包装、nav 高亮
login.html          # 登录页 (无 nav bar)
index.html          # 仪表盘
accounts.html       # 账号管理
settings.html       # 参数配置
```

### 共享 UX 规则

- 每个后台 HTML `<script src="admin.js?v=N">`，版本号 N 单调递增（同用户 SPA 模式）
- `admin.js` 启动时调用 `requireAdmin()` → `GET /api/admin/me`；401 时 `window.location = '/admin/login'`
- 顶部 nav：`[仪表盘] [账号] [设置]` —— 当前页加 `.active`
- 右上角：`当前用户` + `[退出]` 按钮 → `POST /api/admin/logout` → 跳登录页
- 所有 fetch 默认 `credentials: "include"`
- 共享 toast：底部居中弹出 2.5s 自动消失
- 错误码 401 → 跳登录；其他 4xx/5xx → toast 报错

### 页面内容

**`/admin/login`**
- 居中卡片，标题 `AI 辅导员 · 管理后台`
- 用户名 + 密码输入框 + `登录` 按钮
- 错误：toast `用户名或密码错误` 或 `账号已被锁定`
- 成功：`window.location = '/admin'`
- 不显示「默认 admin/147369」提示（安全性）

**`/admin`（仪表盘）**
- 欢迎语：「欢迎，{username}」
- 当前生效配置摘要卡（只读）：四个 section 的关键字段折叠展示
- 重建索引 section：
  - checkbox `[ ] 强制重建（force）`
  - 按钮 `[ 重建索引 ]`
  - 点按钮 → 二次确认 modal：`将扫描 ./Documents，可能耗时较长`
  - 确认 → `POST /api/admin/reindex?force=true|false`
  - loading 期间禁用按钮 + 文字 `处理中…`
  - 返回后展示结果表：`added: N / skipped: M / failed: K`，每行 `path / status / reason`
- 最近索引结果：读取 `GET /api/admin/settings` 之外单独一个 `GET /api/admin/last-reindex`
  - 显示上次重建的时间戳、`added/skipped/failed` 计数、是否需要关注

**`/admin/accounts`**
- 表格列：用户名 / 创建时间 / 最后登录 / 状态 / 操作
- 状态列：`正常`（绿色）/ `已锁定`（红色）
- 操作列：编辑（铅笔） / 解锁（仅锁定时显示） / 删除（红色）
- 顶部按钮 `+ 新增管理员`
- **新增 modal**：用户名 + 密码 + 确认密码；提交前客户端校验匹配
- **编辑 modal**（自己）：用户名只读 + `原密码` + `新密码` + `确认新密码`
- **编辑 modal**（他人）：用户名只读 + `新密码` + `确认新密码`
- **解锁**：调 `PATCH /accounts/{id} {unlock: true}`，成功后表格刷新
- **删除**：调 `DELETE /accounts/{id}`，弹确认 modal `确认删除 {username}?`

**`/admin/settings`**
- 4 个分 section 的折叠卡片（默认全展开）
- 每 section 有独立的 `保存` 按钮和 `恢复默认` 按钮
- 黄色常驻横幅：`修改标有「需重启」的项需重启服务才能生效`
- LLM 推理参数：temperature (slider 0–2, step 0.1), max_tokens (number), top_p (slider 0–1), frequency_penalty (slider -2–2), presence_penalty (slider -2–2) —— **热生效**
- LLM 连接：base_url, model_name, timeout —— **需重启**
- 检索：k, chunk_size, chunk_overlap —— **热生效**
- 路径与环境：documents_dir, data_dir, chroma_collection —— **需重启**
- Embedding 模型：model —— **需重启**
- 保存：`PUT /api/admin/settings {sections: {...}}`
- 恢复默认：弹确认 → PUT 该 section 的硬编码默认值

### 静态资源

- 后台 SPA 由 `app/main.py` 通过 `app.mount("/admin", NoStoreStaticFiles(...))` 提供
- 与用户 SPA 同样 `Cache-Control: no-store`，防止旧 JS 缓存 bug

---

## §7. 配置项与热生效

### 默认值（来自 `llm/config.py` 现有常量）

| Section | 字段 | 默认值 | 热生效? |
|---|---|---|---|
| llm | `base_url` | `http://localhost:8848/v1` | ❌ 需重启 |
| llm | `model_name` | `g0chu-Qwen3.6-35B-A3B-NVFP4` | ❌ 需重启 |
| llm | `timeout` | `120` | ❌ 需重启 |
| llm | `temperature` | `0.3` | ✅ |
| llm | `max_tokens` | `2048` | ✅ |
| llm | `top_p` | `1.0` | ✅ |
| llm | `frequency_penalty` | `0.0` | ✅ |
| llm | `presence_penalty` | `0.0` | ✅ |
| retrieval | `k` | `6` | ✅ |
| retrieval | `chunk_size` | `500` | ✅ |
| retrieval | `chunk_overlap` | `80` | ✅ |
| paths | `documents_dir` | `./Documents` | ❌ 需重启 |
| paths | `data_dir` | `./data` | ❌ 需重启 |
| paths | `chroma_collection` | `counselor` | ❌ 需重启 |
| embedding | `model` | `BAAI/bge-m3` | ❌ 需重启 |

### 实现机制

- `llm/config.py`：
  ```python
  @dataclass
  class LLMConfig:
      base_url: str = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8848/v1")
      model_name: str = os.environ.get("MODEL_NAME", "g0chu-Qwen3.6-35B-A3B-NVFP4")
      temperature: float = float(os.environ.get("TEMPERATURE", "0.3"))
      max_tokens: int = int(os.environ.get("MAX_TOKENS", "2048"))
      timeout: int = int(os.environ.get("LLM_TIMEOUT", "120"))
      top_p: float = 1.0
      frequency_penalty: float = 0.0
      presence_penalty: float = 0.0

  _cfg = LLMConfig()
  def get_llm_settings() -> LLMConfig: return _cfg
  def update_llm_settings(**patch) -> None:
      global _cfg
      for k, v in patch.items(): setattr(_cfg, k, v)
  ```
- `llm/client.py::get_llm()` 每次调用 `get_llm_settings()`
- `rag/retriever.py::get_retriever(k=None)` —— `k` 默认从 settings 单例读
- `rag/splitter.py::split()` —— 读 settings 单例的 `chunk_size/chunk_overlap`
- `RAGConfig` / `EmbeddingConfig` 同样实现

### 需重启项的提示

- `PUT /api/admin/settings` 返回的响应里，对每个被修改的 `requires_restart: true` 字段加提示
- 后台 SPA 顶部黄色横幅列出所有 `requires_restart=true` 的字段名
- 重启检测：`GET /api/admin/me` 返回 `startup_time`；SPA 比对上次启动时间与已知重启时间差，超出阈值则清空横幅
- 这是启发式：横幅不清空表示服务尚未重启

---

## §8. 测试策略

基线（今日）：`OFFLINE=1 uv run --extra dev pytest` → **57 passed / 2 skipped**。新测试需保持基线绿，并新增 admin 覆盖。

### 新增测试文件

**`tests/test_admin_db.py`** — SQLite 持久化
- 缺失 `data/admin.db` → 自动建表 + 种子默认 admin
- 重复连接同一文件 → schema 幂等（`IF NOT EXISTS`）
- `create_account` 同名重复 → `IntegrityError`
- `delete_account` 触发 `ON DELETE CASCADE` 删除其 sessions
- `cleanup_expired_sessions` 只删过期、保留未过期
- `increment_failed_attempts` 返回新计数；连续调用累加正确
- 并发 `set_setting` 序列化（5 个线程同时写不同 section；最终都落盘，无覆盖）
- WAL 模式启用：`PRAGMA journal_mode` 返回 `wal`
- `reset_for_tests()` 删除文件后下一次调用重新建表

**`tests/test_admin_auth.py`** — 密码 & 会话
- `hash_password` + `verify_password` 往返
- 同密码两次哈希产生不同 hash（盐随机）
- 错误密码 → `verify_password` 返回 False（`hmac.compare_digest`）
- `create_session` 返回 URL-safe 32 字符；`get_session` 命中
- `get_session` 过期返回 None
- `touch_session` 延长 `expires_at`
- `login_attempt` 6 次错误后账号 `locked=1`

**`tests/test_admin_accounts.py`** — CRUD + 锁定
- `login_attempt('admin', '147369')` 在全新 DB → 成功 + session 创建
- `login_attempt('admin', 'wrong')` × 5 → 第 6 次 `locked=1`
- 锁定账号用正确密码仍被拒
- 成功登录后 `failed_attempts=0`（但 `locked` 仍为 1，需独立解锁）
- `create_account` 拒重复用户名、弱密码、非法字符用户名
- `delete_account(自己)` 抛错
- `delete_account` 唯一管理员时抛错
- 改自己密码：错 `old_password` → 失败
- 改他人密码：不需要 `old_password`
- 解锁自己 → 抛错
- 解锁他人：成功且 `failed_attempts=0`

**`tests/test_admin_settings.py`** — 配置 CRUD + 热生效
- 缺失 settings → `get_all_settings()` 返回 env defaults
- 写入 `llm.temperature=0.7` → `get_llm_settings().temperature == 0.7`
- 写入 `retrieval.k=10` → `get_retriever().search_kwargs['k'] == 10`
- 写入 `retrieval.chunk_size=300` → splitter 使用新值（mock 调用并断言）
- 越界：`temperature=3.0` → 400
- 类型错：`temperature="abc"` → 400
- 必填缺：`{sections: {}}` → 200（无变更）
- `set_setting` 写入 `updated_by` 字段
- `set_setting('llm', {...}, 'admin')` 后 `get_setting('llm')` 返回相同内容

**`tests/test_admin_routes.py`** — FastAPI 集成
- `POST /api/admin/login` 成功 → 200 + Set-Cookie
- `POST /api/admin/login` 错密码 → 401，不下发 cookie
- `POST /api/admin/login` 第 6 次失败 → 423 + DB 中 `locked=1`
- 所有 gated 端点（`/accounts`、`/settings`、`/reindex`）无 cookie → 401
- 过期 cookie → 401（mock `time.time`）
- `POST /api/admin/reindex` 返回 `IndexResult` 同 shape
- `POST /api/admin/reindex?force=true` 传 `force=True`
- 跨域 POST 携带错误 `Origin` → 403；GET 同条件 → 200（GET 豁免）
- `POST /api/admin/reindex` 两次并发：第二次得 409（reindex lock）
- 后台 SPA 静态页面：`/admin/login.html`、`/admin/index.html` 等都返回 200

**`tests/test_admin_static.py`** — 后台 SPA smoke
- 所有 4 个后台 HTML 文件存在
- 每个 HTML 引用 `admin.js` 和 `admin.css`
- `admin.js` `?v=N` 缓存破坏号单调递增
- 镜像现有 `tests/test_api.py::test_frontend_cache_bust_is_vN` 的模式

### Fixtures (`tests/conftest.py` 新增)

```python
@pytest.fixture(autouse=True)
def _reset_admin_state(tmp_path, monkeypatch):
    """每次测试前把 admin DB 指向 tmp_path，并重置单例。"""
    db = tmp_path / "admin.db"
    monkeypatch.setattr("storage.admin_db._DB_PATH", str(db))
    storage.admin_db.reset_for_tests()
    yield
    storage.admin_db.reset_for_tests()

@pytest.fixture
def admin_client():
    """FastAPI TestClient，admin DB 已在 tmp_path。"""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c

@pytest.fixture
def logged_in_admin(admin_client):
    """预登录的管理员客户端 + session_id + username。"""
    r = admin_client.post("/api/admin/login",
                          json={"username": "admin", "password": "147369"})
    assert r.status_code == 200
    sid = r.cookies.get("counselor_admin")
    return admin_client, sid, "admin"
```

### 修改测试

- `tests/test_api.py` —— 加：
  ```python
  def test_reindex_button_removed():
      assert 'id="reindex"' not in (WEB_DIR / "index.html").read_text()
      assert "reindexBtn" not in (WEB_DIR / "app.js").read_text()

  def test_ingest_route_removed():
      r = client.get("/api/ingest")  # 或 post
      assert r.status_code == 404
  ```
- `tests/test_api.py` —— 如果现有断言含 `id="reindex"` 或 `/api/ingest`，全部删除

### 测试覆盖目标

新测试约 **30 个，~70 个断言**。总目标：**~85 passed / 2 skipped**。

---

## §9. 错误处理

### HTTP 状态码

| 场景 | 状态 |
|---|---|
| 登录：用户名或密码错 | 401 `invalid credentials` |
| 登录：账号已锁 | 423 `account locked` |
| 任意受保护路由：无 cookie | 401 `unauthenticated` |
| 任意受保护路由：cookie 过期 | 401 `session expired` |
| 账号 CRUD：删除最后一个管理员 | 400 |
| 账号 CRUD：删除自己 | 400 |
| 账号 CRUD：自我解锁 | 400 |
| 账号 CRUD：密码 < 6 字符 | 400 |
| 账号 CRUD：用户名非法字符/长度 | 400 |
| 账号 CRUD：用户名重复 | 409 |
| 账号 CRUD：账号不存在 | 404 |
| 配置：类型错或越界 | 400 + 字段错误 |
| 重建索引：正在运行 | 409 |
| 重建索引：Chroma 失败 | 500 + 截断错误 |
| 跨域 POST 错 Origin | 403 |
| 静态：后台页面不存在 | 404（FastAPI 默认） |

### 并发 / 竞态

- **重建索引并发**：模块级 `threading.Lock` 包裹 `build_index`；第二次调用得 409
- **账号并发编辑**：`admin_db._WRITE_LOCK` 串行化写；last-write-wins；密码修改是单事务（读→改→写在锁内）
- **session 清理与请求竞态**：`get_session()` 内惰性删除过期；正在被使用的 session 不会因此失效

### 文件系统弹性

- DB 文件损坏（`sqlite3.DatabaseError`）→ 重命名为 `data/admin.db.broken-{ts}` + 重建 + 重新种子默认账号；stderr 警告
- WAL 模式自动崩溃恢复
- 权限拒绝 / 磁盘满 → 500 直接传播

### CSRF / 跨域

- `SameSite=Lax` 拦大多数跨站请求
- 额外保护：所有 mutating 端点 (`POST/PUT/PATCH/DELETE`) 验证 `Origin` header 与配置的 `COUNSELOR_ALLOWED_ORIGIN`（默认 `http://localhost:8000`）一致；不一致 → 403
- GET 端点不验证

### 默认账号警告

- 首次种子默认 admin/147369 时 stderr 打印两行提示（见 §3）
- README + CLAUDE.md 明确：首次登录后**必须**改密
- 不强制改密流程（admin 可选择延后，但提示到位）

### 日志

```
[admin] 2026-07-25T22:00:00 login_ok username=admin session_id=abc123
[admin] 2026-07-25T22:00:01 login_fail username=admin reason=invalid_credentials
[admin] 2026-07-25T22:00:07 login_fail username=admin reason=invalid_credentials failed_attempts=6 locked=true
[admin] 2026-07-25T22:01:00 account_create username=newadmin by=admin
[admin] 2026-07-25T22:02:00 settings_update section=llm by=admin
[admin] 2026-07-25T22:03:00 reindex_start force=true by=admin
[admin] 2026-07-25T22:05:30 reindex_done added=12 skipped=3 failed=0 duration_s=150
[admin] 2026-07-25T22:10:00 logout username=admin session_id=abc123
```

- 全部 stderr
- 单进程本地服务，不需要 ELK / 文件日志轮转

---

## §10. 范围之外（YAGNI）

明确**不**在本次设计内：
- ❌ 用户级别账号（仅管理员；聊天仍匿名、无状态）
- ❌ 服务端持久化聊天历史（沿用 localStorage-only）
- ❌ 审计日志 UI（仅 stderr）
- ❌ 邮件密码重置
- ❌ 二次验证 / MFA
- ❌ 多角色权限（仅 admin）
- ❌ HTTPS / TLS 终止（本地 HTTP）
- ❌ 限流（锁定机制足够）
- ❌ Admin API 版本前缀（`/api/admin/v1`）
- ❌ 安全问题找回
- ❌ WebSocket 流式重建索引进度
- ❌ Admin 查看/回放聊天历史（后端无数据可展示）
- ❌ Admin 修改 agent prompt / 代码（prompts.py 是代码不是配置）

---

## §11. 迁移与部署

### 用户视角
- 用户**无感知**：聊天 SPA 删除一个按钮而已
- 所有 localStorage 会话继续可用
- `data/chroma/` 和 `data/index_meta.json` 不动
- `data/checkpoints.db` 早已由 `run.sh` 删除

### 管理员视角
1. `bash scripts/run.sh` 启动服务（无变化）
2. 浏览器访问 `http://localhost:8000/admin/login`
3. 用 `admin` / `147369` 登录
4. **立即**改密码（`/admin/accounts`）
5. 在 `/admin/settings` 按需调整参数
6. 在 `/admin` 触发首次重建（如需强制刷新）

### 自动创建
- `data/admin.db` 在第一次访问 `/api/admin/*` 时自动创建
- 默认 admin 账号自动种子

### 文档更新清单
- `CLAUDE.md`：加 管理后台 子节；更新包结构表；记默认账号
- `README.md`：加 管理后台 子节；附 `/admin/login` 链接 + 默认凭据警告
- 本设计文档（`docs/superpowers/specs/2026-07-25-admin-backend-design.md`）

### 实施计划
- 设计批准后由 `writing-plans` skill 拆解为 12–15 个子任务，每个含实现 + 评审 + 测试，目标工时 8–12 小时