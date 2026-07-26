# AI Counselor — LLM API Key 支持 (LLM API Key)

> 让 `llm/` 包发送给上游 LLM 服务时附带 API key（默认 `"llama.cpp"`），
> 既兼容本地 llama.cpp（不校验 key），又能直接对接 OpenAI / Azure / 其他需要鉴权的
> OpenAI 兼容服务，免去用户改源码。

---

## §1. 架构总览

数据流不变；改两点：
- `get_llm()` 把硬编码 `api_key="not-needed"` 换成 `cfg.api_key`（`ChatOpenAI` 内部自动加 `Authorization: Bearer <key>` 头）。
- `_probe_llm()` 显式给 `urllib.request.Request` 加 `Authorization: Bearer <key>` 头（裸 `urlopen` 不能传 header）。

```
Browser
  ├─ WS chat ───► app/routes_chat.py ───► llm/client.py::get_llm() ──► ChatOpenAI(api_key=cfg.api_key)
  │                                                                              │ (langchain-openai 隐式加)
  │                                                                              ▼
  │                                                                       upstream LLM
  └─ GET /api/health ──► app/routes_health.py::_probe_llm() ──► urllib Request GET /v1/models
                                                                       Authorization: Bearer <cfg.api_key>

Admin SPA ─► PUT /api/admin/settings ──► app/admin/settings.py::update_settings()
                                          └─► 改 llm/config.py::_llm_cfg 单例字段 in-place（热生效，下次请求即时生效）
```

关键约束：
- 沿用现有「配置单例 + in-place 更新」模式（`llm/config.py` 已为 `temperature` / `max_tokens` 等热生效字段建立此模式）。
- 不引入新的重启类型；`api_key` 与 `temperature` / `max_tokens` 同列，归类为「热生效」。
- `app/routes_health.py::_probe_llm` 的 10s TTL 缓存逻辑不变（缓存的是 bool，api_key 改动 → 下一周期重探测即生效）。

---

## §2. 组件与文件结构

### 修改文件

| 文件 | 变更 |
|---|---|
| `llm/config.py` | `LLMConfig` 加 `api_key: str` 字段；`_build_llm_defaults()` 从 `LLAMACPP_API_KEY` 环境变量读取，默认 `"llama.cpp"`。**不**新增模块级常量（与 `temperature` 等字段一致，统一走 `get_llm_settings()` getter）。 |
| `llm/client.py` | `get_llm()` 把 `api_key="not-needed"` 替换为 `api_key=s.api_key`。 |
| `app/routes_health.py` | `_probe_llm()` 用 `urllib.request.Request` + 显式 `Authorization: Bearer <key>` 头（从 `get_llm_settings().api_key` 读）。 |
| `app/admin/settings.py` | `DEFAULTS["llm"]` 新增 `"api_key": "llama.cpp"`；`_STR_FIELDS` 新增 `("llm", "api_key")`（非空字符串校验，与 `base_url` 同规则）；`REQUIRES_RESTART["llm"]` **不**加 `api_key`（热生效）。 |
| `app/admin/schemas.py` | `LLMSettings`（Pydantic schema）新增 `api_key: str` 字段。 |
| `tests/test_llm.py` | 新增默认 + 环境变量覆盖测试；修改 `test_get_llm_uses_openai_compat` 断言 `llm.openai_api_key == "llama.cpp"`。 |
| `tests/test_admin_settings.py` | 新增 api_key round-trip / 校验 / 重启断言；扩展默认检查。 |
| `tests/test_api.py` 或 `test_admin_routes.py` | 如有 `/api/health` 探针 mock，新增「带 Authorization 头」断言（如未覆盖，则新增一条 focused 测试）。 |
| `CLAUDE.md` | 环境变量表新增 `LLAMACPP_API_KEY | llama.cpp | llama.cpp OpenAI 兼容端点 API key（默认 "llama.cpp"；切换到需鉴权的云服务时覆盖）`。 |

### 不修改

- `agent/` 包（不感知 api_key；通过 `get_llm()` 间接拿到）
- `app/routes_chat.py`（同上层理由）
- `storage/admin_db.py`（存储层无 schema 变更；api_key 作为 `settings.llm` JSON 字段中的普通 key 入库）
- 前端（管理后台 SPA 自动从 `GET /api/admin/settings` 的 `sections.llm` 读 api_key；现有的 settings 渲染逻辑对所有 llm 字段一视同仁，**前提是** input 的 name 与 schema 字段名一致——见 §6）

---

## §3. 配置层（`llm/config.py`）

```python
@dataclass
class LLMConfig:
    base_url: str
    model_name: str
    api_key: str          # 新增
    temperature: float
    ...


def _build_llm_defaults() -> LLMConfig:
    return LLMConfig(
        base_url=_env("LLAMACPP_BASE_URL", "http://localhost:8848/v1"),
        model_name=_env("MODEL_NAME", "g0chu-Qwen3.6-35B-A3B-NVFP4"),
        api_key=_env("LLAMACPP_API_KEY", "llama.cpp"),  # 新增
        temperature=float(_env("TEMPERATURE", "0.3")),
        ...
    )
```

- 不新增模块级 `LLAMACPP_API_KEY` 导出（没有 `app/routes_health.py` 这种 import-time 读取的旧代码依赖）。
- `reset_settings_for_tests()` 自然重建，无需改动（已 rebuild 整个单例）。

---

## §4. 客户端层（`llm/client.py` + `app/routes_health.py`）

### `llm/client.py`

```python
def get_llm(*, streaming: bool = True) -> ChatOpenAI:
    s = get_llm_settings()
    return ChatOpenAI(
        base_url=s.base_url,
        api_key=s.api_key,            # 改：移除硬编码 "not-needed"
        model=s.model_name,
        streaming=streaming,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
        timeout=s.timeout,
    )
```

`langchain_openai.ChatOpenAI` 会把 `api_key` 写到 `openai_api_key` 属性，并加 `Authorization: Bearer <key>` 头（`langchain-openai ≥ 0.1` 已是标准行为；项目已 lock 的版本满足）。

### `app/routes_health.py::_probe_llm`

```python
from urllib.request import Request, urlopen

from llm.config import LLAMACPP_BASE_URL, get_llm_settings

def _probe_llm() -> bool:
    api_key = get_llm_settings().api_key
    req = Request(
        f"{LLAMACPP_BASE_URL.rstrip('/')}/models",   # 沿用模块级常量，不跟随 admin hot-reload
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urlopen(req, timeout=2.0) as response:
            return response.status == 200
    except Exception:
        return False
```

- 改裸 `urlopen(url)` → `urlopen(Request(url, headers={...}))`。
- 本地 llama.cpp 不校验 token，多发一个 `Authorization` 头是无害的（服务端会忽略）。
- 对 OpenAI / Azure OpenAI / 其他需鉴权的 OpenAI 兼容代理：探活才能返回 200，避免 `/api/health` 永远报 `degraded`。
- `base_url` 仍走模块级 `LLAMACPP_BASE_URL`（import-time 捕获，不跟随 admin hot-reload），与现有 admin 文档「`base_url` 改完需重启」约定一致；**仅** `api_key` 走 `get_llm_settings()`，因为 api_key 是热生效字段。

---

## §5. 管理后台设置

### `app/admin/settings.py::DEFAULTS["llm"]`

```python
"llm": {
    "base_url": "http://localhost:8848/v1",
    "model_name": "g0chu-Qwen3.6-35B-A3B-NVFP4",
    "api_key": "llama.cpp",          # 新增
    "temperature": 0.3,
    "max_tokens": 2048,
    "timeout": 120,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
},
```

### `_STR_FIELDS`

```python
_STR_FIELDS: set[tuple[str, str]] = {
    ("llm", "base_url"), ("llm", "model_name"), ("llm", "api_key"),  # 新增最后一项
    ...
}
```

校验规则：非空字符串（与 `base_url` 一致）。空串 → `InvalidFieldError` → 422。

### `REQUIRES_RESTART["llm"]`

```python
"llm": {"base_url", "model_name", "timeout"},   # 不变：api_key 热生效
```

理由：`get_llm()` 是每次 WS 请求重新调用，从单例读 `_llm_cfg.api_key`；admin 改完即刻生效。

### `app/admin/schemas.py::LLMSettings`

```python
class LLMSettings(BaseModel):
    base_url: str
    model_name: str
    api_key: str      # 新增
    temperature: float
    max_tokens: int
    timeout: int
    top_p: float
    frequency_penalty: float
    presence_penalty: float
```

无 `Field(min_length=...)` / `max_length`：长短不限（API key 形态多样），只由 `_validate_section_payload` 的 `_STR_FIELDS` 检查非空。

### `GET /api/admin/settings` 回显策略

保留现状：`get_effective_settings()` 返回 `api_key` 原文。理由：
- 管理员已认证（session cookie）
- 显示给可信管理员便于核对（无需来回切换）
- 不在 admin_session / 普通日志里打印（`db_settings.set()` 只存 value，不打日志）

---

## §6. 前端（自动适配）

`web/admin/settings.html` 的现有表单渲染逻辑（`renderForm` / `renderLLMSettings`）遍历 `DEFAULTS.llm` 的 keys 生成 `<input name="...">`。新增 `api_key` 后会自动出现一个 `<input type="text" name="api_key">` 字段——前提是 input 的 `name` 与 schema 字段一致（已确认现有实现是 `Object.entries(DEFAULTS[section]).forEach(([k, v]) => ...)` 风格）。

需要核对的内容：
- `web/admin/settings.html::renderLLMSettings`（或同位函数）：确认遍历 `Object.entries()` 而非硬编码字段列表。
- 如果硬编码了字段列表 → 加 `api_key: { ... }` 一行（input type 设为 `password` 防止旁观者窥屏；这是 nice-to-have，非必需，因为 admin_session 已要求登录；本次实施若发现硬编码则顺手改为 password）。

如果最终发现需要前端改动，会作为「同一任务的最小前端适配」在 plan 里列出；不另行 spec。

---

## §7. 错误处理

| 场景 | 行为 |
|---|---|
| Admin POST `{"api_key": ""}` | 400 / `InvalidFieldError` (`settings.llm.api_key must be non-empty string`) |
| Admin POST `{"api_key": null}` | 400（`SettingsPatch.sections` 是 `dict[str, dict[str, Any]]` 不跑 Pydantic 内层验证，由 `_validate_section_payload` 的 `isinstance(value, str)` 检查拒绝） |
| Admin POST `{"api_key": 123}` | 400 / `InvalidFieldError` (`must be non-empty string`) |
| Admin POST `{"api_key": "sk-real"}` | OK；下次 `get_llm()` 即用新 key |
| `LLAMACPP_API_KEY` 环境变量未设 | `LLMConfig.api_key = "llama.cpp"` |
| `LLAMACPP_API_KEY=""` （空字符串） | `LLMConfig.api_key = ""` —— 故意不视为「未设」；环境变量里写空串意味着明确清空。前端 admin 设置仍按「非空」校验；CLI 部署时若想用空 key 需绕开 admin settings 直接走环境变量或重启+settings.json。**记录为已知行为**，不修复。 |
| 上游 LLM 拒签（401/403） | 不在本次范围；属业务调用错误，由 WS handler 的现有 error 事件路径处理（CLAUDE.md §「WebSocket 协议」已有 `error` 事件）。 |
| 长度不限 | API key 形态多样（bge-m3 不要 key / OpenAI sk-.../ Azure 32 位 hex）；不做长度约束。 |

---

## §8. 测试

新增 / 修改用例，全部 OFFLINE=1 友好：

### `tests/test_llm.py`

- **新增** `test_default_api_key`：
  - `monkeypatch.delenv("LLAMACPP_API_KEY", raising=False)`
  - `importlib.reload(cfg)`
  - `assert cfg.get_llm_settings().api_key == "llama.cpp"`
- **新增** `test_env_override_api_key`：
  - `monkeypatch.setenv("LLAMACPP_API_KEY", "sk-test-123")`
  - `importlib.reload(cfg)`
  - `assert cfg.get_llm_settings().api_key == "sk-test-123"`
- **修改** `test_get_llm_uses_openai_compat`：
  - 追加 `assert llm.openai_api_key == "llama.cpp"`

### `tests/test_admin_settings.py`

- **修改** `test_defaults_has_*` 或类似断言 `DEFAULTS["llm"]` 完整性的测试：
  - 加 `"api_key"` key 检查 + 默认值 `"llama.cpp"`
- **新增** `test_api_key_round_trip`：
  - 登录 admin
  - `PUT /api/admin/settings {"sections": {"llm": {"api_key": "sk-test-abc"}}}`
  - `GET /api/admin/settings` 断言回 `"sk-test-abc"`
  - `from llm.config import get_llm_settings; assert get_llm_settings().api_key == "sk-test-abc"`
- **新增** `test_api_key_validation_empty`：
  - `PUT /api/admin/settings {"sections": {"llm": {"api_key": ""}}}` → 422
- **新增** `test_api_key_validation_wrong_type`：
  - `PUT /api/admin/settings {"sections": {"llm": {"api_key": 123}}}` → 422
- **新增** `test_api_key_not_restart_required`：
  - `PUT` 只改 `api_key` → 响应 `restart_required` 为空（断言 `"llm.api_key" not in restart`）

### `tests/test_api.py` 或 `tests/test_admin_routes.py`（按现有惯例放）

- **新增** `test_health_probe_sends_authorization`（OFFLINE）：
  - `monkeypatch.setattr("app.routes_health.urlopen", fake_urlopen)`，`fake_urlopen` 捕获 `Request` 对象
  - 调用 `_probe_llm()`
  - 断言 `request.headers.get("Authorization") == "Bearer llama.cpp"` （默认）
  - 再设 `LLAMACPP_API_KEY=sk-other` reload → 重测 → 断言 `Bearer sk-other`

### 全量回归

`OFFLINE=1 uv run --extra dev pytest -q` 期望通过；新测试 + 老测试一起跑；预期基线数字 + 新增用例数。

---

## §9. 文档更新

`CLAUDE.md` 环境变量表新增一行：

```
| `LLAMACPP_API_KEY` | `llama.cpp` | llama.cpp OpenAI 兼容端点 API key（默认 "llama.cpp"；切换到需鉴权的云服务时覆盖） |
```

环境变量位置：插在 `LLAMACPP_BASE_URL` 之后（同属 `llm/config.py`）。

不修改 `CLAUDE.md` 其他章节（管理后台 / 包结构等无变化）。
不修改 `README.md`（api_key 是新增字段，自动出现在 admin settings 页面，无需用户文档）。

---

## §10. 已知边界 / 不做

- **不做** secret masking / redaction（管理员已认证；本服务单进程本地运行，DB 与 admin 同权限域）
- **不做** key 长度 / 格式校验（OpenAI / Azure / 自建代理差异过大）
- **不做** `/api/health` 鉴权失败（401/403）的细化提示；保持 `_probe_llm()` 仅返回 bool，错误统一走 `degraded`
- **不做** env var `LLAMACPP_API_KEY=""` 的特殊处理（保留为字面空串，与 admin 校验非空不冲突；CLI 部署场景罕见）
- **不做** `LLAMACPP_BASE_URL` 改 `get_llm_settings().base_url`（保留 module-level 常量，避免扩大 PR 范围；与 admin 「base_url 改完需重启」文档约定一致）
- **不做** 加密存储 api_key（`storage/admin_db.py` 已存 SQLite 明文；加密会引入 keyring / KMS 依赖，与本项目「本地单进程」定位冲突）