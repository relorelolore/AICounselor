# LLM API Key 支持 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 LLM 客户端和 `/api/health` 探针在请求时附带 API key（默认 `"llama.cpp"`），并把 key 暴露到管理后台 `PUT /api/admin/settings`，便于对接需鉴权的 OpenAI 兼容服务（OpenAI / Azure / 自建代理）。

**Architecture:** 沿用现有「`LLMConfig` 单例 + in-place 更新」模式。新增 `api_key: str` 字段，`LLAMACPP_API_KEY` 环境变量默认 `"llama.cpp"`。`get_llm()` 改用 `s.api_key` 替换硬编码 `"not-needed"`；`_probe_llm()` 显式给 `urllib.request.Request` 加 `Authorization: Bearer <key>` 头。管理后台 `LLMSettings` + `DEFAULTS["llm"]` + `_STR_FIELDS` 同步加 `api_key`；`api_key` 归类为热生效（不进 `REQUIRES_RESTART["llm"]`）。

**Tech Stack:** Python 3.12 + FastAPI + langchain-openai + urllib.request + pytest。零新依赖。

## Global Constraints

- 工具链：`uv 0.11+` 管理 `.venv/`；所有 pytest 必须 `uv run --extra dev pytest`（不能直接 `pytest` / `python -m pytest`）。
- OFFLINE 默认：`OFFLINE=1` 跑全量；bge-m3 / live llama.cpp 测试自动 skip。
- 现有约定（CLAUDE.md）：`.gitignore` 根锚定 `/main.py`；`tests/` 无 `__init__.py`；conftest 的 `_reset_llm_config` autouse fixture 每次 importlib.reload `llm.config`，新增 env 覆盖测试仍需 reload。
- 配置单例：`llm/config.py::_llm_cfg` 必须 in-place 更新（admin hot-reload 依赖此行为）。任何只读 `LLMConfig(...)` 然后替换 `_llm_cfg` 的写法会破坏现有逻辑。
- Spec：`docs/superpowers/specs/2026-07-26-llm-api-key-design.md`（commit `1effd06` + `e14f586`）。
- 不修改：`agent/`、`app/routes_chat.py`、`storage/admin_db.py`、`app/admin/routes.py`（结构不变，仅字段扩展）。不修改前端 SPA（admin settings 自动从 `DEFAULTS["llm"]` 渲染新 input）。

---

### Task 1: `LLMConfig.api_key` 字段 + `LLAMACPP_API_KEY` 环境变量

**Files:**
- Modify: `llm/config.py:15-65` (`LLMConfig` dataclass + `_build_llm_defaults`)
- Test: `tests/test_llm.py` (新增 `test_default_api_key` / `test_env_override_api_key`)

**Interfaces:**
- Consumes: 无新增依赖
- Produces: `LLMConfig.api_key: str`（热生效）；`LLAMACPP_API_KEY` 环境变量

- [ ] **Step 1: 写失败测试 — 默认值**

在 `tests/test_llm.py` 末尾新增：

```python
def test_default_api_key(monkeypatch):
    """LLAMACPP_API_KEY 未设时默认 'llama.cpp'。"""
    monkeypatch.delenv("LLAMACPP_API_KEY", raising=False)
    import importlib, llm.config as cfg
    importlib.reload(cfg)
    assert cfg.get_llm_settings().api_key == "llama.cpp"


def test_env_override_api_key(monkeypatch):
    """LLAMACPP_API_KEY 环境变量覆盖默认值。"""
    monkeypatch.setenv("LLAMACPP_API_KEY", "sk-test-123")
    import importlib, llm.config as cfg
    importlib.reload(cfg)
    assert cfg.get_llm_settings().api_key == "sk-test-123"
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_llm.py::test_default_api_key tests/test_llm.py::test_env_override_api_key -v
```

预期：`AttributeError: 'LLMConfig' object has no attribute 'api_key'`（dataclass 字段缺失）。

- [ ] **Step 3: 实现 — 加字段 + env var**

修改 `llm/config.py`：

1. `LLMConfig` dataclass 在 `model_name` 之后新增 `api_key: str`：

```python
@dataclass
class LLMConfig:
    base_url: str
    model_name: str
    api_key: str          # 新增
    temperature: float
    max_tokens: int
    timeout: int
    top_p: float
    frequency_penalty: float
    presence_penalty: float
```

2. `_build_llm_defaults()` 在 `model_name` 之后新增：

```python
def _build_llm_defaults() -> LLMConfig:
    return LLMConfig(
        base_url=_env("LLAMACPP_BASE_URL", "http://localhost:8848/v1"),
        model_name=_env("MODEL_NAME", "g0chu-Qwen3.6-35B-A3B-NVFP4"),
        api_key=_env("LLAMACPP_API_KEY", "llama.cpp"),  # 新增
        temperature=float(_env("TEMPERATURE", "0.3")),
        max_tokens=int(_env("MAX_TOKENS", "2048")),
        timeout=int(_env("LLM_TIMEOUT", "120")),
        top_p=float(_env("TOP_P", "1.0")),
        frequency_penalty=float(_env("FREQUENCY_PENALTY", "0.0")),
        presence_penalty=float(_env("PRESENCE_PENALTY", "0.0")),
    )
```

**不**新增模块级 `LLAMACPP_API_KEY` 常量（与 `temperature` 一致，统一走 getter）。

- [ ] **Step 4: 跑测试，验证通过**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_llm.py -v
```

预期：`test_default_api_key` / `test_env_override_api_key` PASS，其余保持原状态（3 PASS + 1 SKIP）。

- [ ] **Step 5: 提交**

```bash
git add llm/config.py tests/test_llm.py
git commit -m "feat(llm): add api_key field to LLMConfig (default \"llama.cpp\")"
```

---

### Task 2: `llm/client.py::get_llm()` 使用 `s.api_key`

**Files:**
- Modify: `llm/client.py:7-17`
- Test: `tests/test_llm.py` (修改 `test_get_llm_uses_openai_compat`)

**Interfaces:**
- Consumes: `LLMConfig.api_key` from Task 1
- Produces: `ChatOpenAI(api_key=s.api_key)` 内部自动加 `Authorization: Bearer <key>`

- [ ] **Step 1: 修改现有测试**

在 `tests/test_llm.py::test_get_llm_uses_openai_compat` 末尾追加断言（保留原断言）：

```python
def test_get_llm_uses_openai_compat(monkeypatch):
    """get_llm 必须基于 ChatOpenAI 指向 OpenAI-compatible base url。"""
    from langchain_openai import ChatOpenAI
    from llm.client import get_llm
    from llm.config import update_llm_settings
    update_llm_settings({"temperature": 0.0})
    llm = get_llm(streaming=False)
    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == "http://localhost:8848/v1"
    assert llm.model_name == "g0chu-Qwen3.6-35B-A3B-NVFP4"
    assert llm.streaming is False
    assert llm.temperature == 0.0
    assert llm.openai_api_key == "llama.cpp"  # 新增
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_llm.py::test_get_llm_uses_openai_compat -v
```

预期：FAIL `assert llm.openai_api_key == "llama.cpp"`，实际为 `"not-needed"`。

- [ ] **Step 3: 实现**

修改 `llm/client.py`：

```python
# llm/client.py
from langchain_openai import ChatOpenAI

from .config import get_llm_settings


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

- [ ] **Step 4: 跑测试，验证通过**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_llm.py -v
```

预期：全部 PASS（含 Task 1 的 2 个新测试 + 本任务的修改测试）。

- [ ] **Step 5: 提交**

```bash
git add llm/client.py tests/test_llm.py
git commit -m "feat(llm): client.py uses configured api_key (was hardcoded \"not-needed\")"
```

---

### Task 3: `/api/health` 探针加 `Authorization: Bearer <key>`

**Files:**
- Modify: `app/routes_health.py:1-43`（`_probe_llm()` 函数 + 顶部 import）
- Test: `tests/test_api.py` (新增 `test_health_probe_sends_authorization`)

**Interfaces:**
- Consumes: `LLMConfig.api_key` from Task 1
- Produces: 每次 `_probe_llm()` 发出的 HTTP 请求带 `Authorization: Bearer <cfg.api_key>` 头

- [ ] **Step 1: 写失败测试**

在 `tests/test_api.py` 末尾新增：

```python
def test_health_probe_sends_authorization(monkeypatch):
    """_probe_llm 必须在 GET /v1/models 上带 Authorization: Bearer <key>。"""
    import importlib
    import llm.config as cfg
    importlib.reload(cfg)  # ensure default "llama.cpp"

    captured = {}

    class _FakeResp:
        status = 200

    def fake_urlopen(req, timeout=2.0):
        captured["req"] = req
        captured["auth"] = req.headers.get("Authorization")
        return _FakeResp()

    from app import routes_health
    monkeypatch.setattr(routes_health, "urlopen", fake_urlopen)
    # Skip TTL cache from previous test runs.
    monkeypatch.setattr(routes_health, "_probe_cache", None)
    monkeypatch.setattr(routes_health, "_probe_lock", __import__("threading").Lock())

    assert routes_health._probe_llm() is True
    assert captured["auth"] == "Bearer llama.cpp"

    # Env override → next probe uses new key
    monkeypatch.setenv("LLAMACPP_API_KEY", "sk-other")
    importlib.reload(cfg)
    monkeypatch.setattr(routes_health, "urlopen", fake_urlopen)
    monkeypatch.setattr(routes_health, "_probe_cache", None)
    monkeypatch.setattr(routes_health, "_probe_lock", __import__("threading").Lock())
    captured.clear()
    assert routes_health._probe_llm() is True
    assert captured["auth"] == "Bearer sk-other"
```

**注意**：测试用了 `monkeypatch.setattr(routes_health, "_probe_cache", None)` 强制绕过 10s TTL；`_probe_lock` 重置避免线程模型状态污染。如 conftest 的 `_reset_llm_config` 已 reload `llm.config`，第一次 reload 是幂等的。

- [ ] **Step 2: 跑测试，验证失败**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_api.py::test_health_probe_sends_authorization -v
```

预期：FAIL（裸 `urlopen` 不带 Authorization，`captured["auth"]` 为 `None`）。

- [ ] **Step 3: 实现**

修改 `app/routes_health.py`：

1. 顶部 import 改为：

```python
# app/routes_health.py
from __future__ import annotations

import time
from threading import Lock
from urllib.request import Request, urlopen

from fastapi import APIRouter

from llm.config import LLAMACPP_BASE_URL, get_llm_settings
from rag.retriever import collection_count

from .schemas import HealthResponse
```

2. `_probe_llm()` 改为：

```python
def _probe_llm() -> bool:
    """Quick HTTP probe of the llama.cpp /v1/models endpoint.

    Sends Authorization: Bearer <api_key> so authenticated OpenAI-compatible
    proxies (OpenAI / Azure / etc.) also probe green; llama.cpp ignores the
    header.
    """
    api_key = get_llm_settings().api_key
    req = Request(
        f"{LLAMACPP_BASE_URL.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urlopen(req, timeout=2.0) as response:
            return response.status == 200
    except Exception:
        return False
```

`base_url` 仍走模块级 `LLAMACPP_BASE_URL`（不动 `_probe_llm` 的 base_url 来源，与「base_url 改完需重启」约定一致）；仅 `api_key` 走 `get_llm_settings()`。

- [ ] **Step 4: 跑测试，验证通过**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_api.py -v
```

预期：全部 PASS（含原有 `test_health_returns_struct` + 本任务新测试）。

- [ ] **Step 5: 提交**

```bash
git add app/routes_health.py tests/test_api.py
git commit -m "feat(health): /api/health probe sends Authorization: Bearer <api_key>"
```

---

### Task 4: 管理后台 `DEFAULTS` + `_STR_FIELDS` + `LLMSettings` 加 `api_key`

**Files:**
- Modify: `app/admin/settings.py:11-68`
- Modify: `app/admin/schemas.py:54-62`
- Test: `tests/test_admin_settings.py` (扩展 `test_defaults_contain_every_field`)

**Interfaces:**
- Consumes: 无新增依赖
- Produces: `DEFAULTS["llm"]["api_key"] = "llama.cpp"`；`_STR_FIELDS` 含 `("llm", "api_key")`；`LLMSettings` schema 含 `api_key: str`

- [ ] **Step 1: 扩展现有测试**

修改 `tests/test_admin_settings.py::test_defaults_contain_every_field`：

```python
def test_defaults_contain_every_field():
    assert set(DEFAULTS["llm"].keys()) == {
        "base_url", "model_name", "api_key", "temperature", "max_tokens",
        "timeout", "top_p", "frequency_penalty", "presence_penalty",
    }
    assert DEFAULTS["llm"]["api_key"] == "llama.cpp"
    assert set(DEFAULTS["retrieval"].keys()) == {"k", "chunk_size", "chunk_overlap"}
    assert set(DEFAULTS["paths"].keys()) == {
        "documents_dir", "data_dir", "chroma_collection",
    }
    assert set(DEFAULTS["embedding"].keys()) == {"model"}
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_admin_settings.py::test_defaults_contain_every_field -v
```

预期：FAIL `assert "api_key" in DEFAULTS["llm"].keys()`。

- [ ] **Step 3: 实现**

修改 `app/admin/settings.py`：

1. `DEFAULTS["llm"]` 在 `model_name` 之后新增：

```python
DEFAULTS: dict[str, dict] = {
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
    "retrieval": { ... },  # 不变
    "paths": { ... },       # 不变
    "embedding": { ... },   # 不变
}
```

2. `_STR_FIELDS` 集合在 `("llm", "model_name")` 后新增：

```python
_STR_FIELDS: set[tuple[str, str]] = {
    ("llm", "base_url"), ("llm", "model_name"), ("llm", "api_key"),  # 新增最后一项
    ("paths", "documents_dir"), ("paths", "data_dir"), ("paths", "chroma_collection"),
    ("embedding", "model"),
}
```

3. `REQUIRES_RESTART["llm"]` **不**改（`api_key` 热生效）。

修改 `app/admin/schemas.py`：

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

- [ ] **Step 4: 跑测试，验证通过**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_admin_settings.py -v
```

预期：全部 PASS（含本任务扩展测试 + 已有 22 个测试）。

- [ ] **Step 5: 提交**

```bash
git add app/admin/settings.py app/admin/schemas.py tests/test_admin_settings.py
git commit -m "feat(admin): expose api_key in /api/admin/settings (defaults + schema + validation)"
```

---

### Task 5: 管理后台 `PUT /api/admin/settings` round-trip + 热生效测试

**Files:**
- Test only: `tests/test_admin_routes.py` (新增 4 个测试)

**Interfaces:**
- Consumes: `update_settings(sections={"llm": {"api_key": ...}})` from Task 4 + `get_llm_settings()` from Task 1
- Produces: 端到端验证 api_key 入库 → GET 回显 → 单例 hot-reload；验证空串/非字符串校验；验证不在 `restart_required` 列表

- [ ] **Step 1: 写测试 — round-trip + hot-reload**

在 `tests/test_admin_routes.py` 末尾新增：

```python
# ----- /settings api_key -----

def test_settings_round_trip_api_key(logged_in, monkeypatch):
    """PUT → DB → GET → 单例：api_key 端到端走通且热生效。"""
    import importlib, llm.config as llm_cfg

    # 确保起点干净
    importlib.reload(llm_cfg)
    assert llm_cfg.get_llm_settings().api_key == "llama.cpp"

    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"api_key": "sk-test-abc"}}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sections"]["llm"]["api_key"] == "sk-test-abc"
    # Not restart-required (hot-reload).
    assert "llm.api_key" not in body["restart_required"]

    # GET 回显
    g = logged_in.get("/api/admin/settings")
    assert g.status_code == 200
    assert g.json()["sections"]["llm"]["api_key"] == "sk-test-abc"

    # 单例 hot-reload
    assert llm_cfg.get_llm_settings().api_key == "sk-test-abc"


def test_settings_api_key_validation_empty_string(logged_in):
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"api_key": ""}}},
    )
    assert r.status_code == 422, r.text


def test_settings_api_key_validation_wrong_type(logged_in):
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"api_key": 123}}},
    )
    assert r.status_code == 422, r.text


def test_settings_api_key_not_restart_required(logged_in):
    """只改 api_key 时 restart_required 列表为空。"""
    r = logged_in.put(
        "/api/admin/settings",
        json={"sections": {"llm": {"api_key": "sk-xyz"}}},
    )
    assert r.status_code == 200
    assert r.json()["restart_required"] == []
```

- [ ] **Step 2: 跑测试，验证全部 PASS**

```bash
OFFLINE=1 uv run --extra dev pytest tests/test_admin_routes.py -v -k "api_key"
```

预期：4 个新测试全 PASS（schema + validation + round-trip + restart-required 由 Task 4 间接支撑）。

- [ ] **Step 3: 提交**

```bash
git add tests/test_admin_routes.py
git commit -m "test(admin): api_key round-trip / validation / restart-required coverage"
```

---

### Task 6: `CLAUDE.md` 环境变量表 + 全量回归

**Files:**
- Modify: `CLAUDE.md`（环境变量表新增一行）
- Test: 跑全量回归

**Interfaces:**
- Consumes: 无
- Produces: `CLAUDE.md` 列出 `LLAMACPP_API_KEY`

- [ ] **Step 1: 修改 `CLAUDE.md`**

定位到「环境变量」表格中 `LLAMACPP_BASE_URL` 那行，在其后插入：

```markdown
| `LLAMACPP_API_KEY` | `llama.cpp` | llama.cpp OpenAI 兼容端点 API key（默认 `"llama.cpp"`；切换到需鉴权的云服务时覆盖） |
```

- [ ] **Step 2: 跑全量回归**

```bash
OFFLINE=1 uv run --extra dev pytest -q
```

预期：基线 `195 passed, 2 skipped`（+ Task 1–5 新增测试 ≈ 9 个新 PASS）。如有 failure，立刻定位修复，**不要**继续 Step 3。

- [ ] **Step 3: 提交**

```bash
git add CLAUDE.md
git commit -m "docs(claude): document LLAMACPP_API_KEY env var"
```

---

## Self-Review Checklist（实现者跳过此段，写 plan 时已做）

- [x] Spec §3 配置层 → Task 1
- [x] Spec §4.1 client.py → Task 2
- [x] Spec §4.2 routes_health.py → Task 3
- [x] Spec §5 DEFAULTS + _STR_FIELDS + LLMSettings → Task 4
- [x] Spec §7 错误处理（空串 / 非字符串 / null）→ Task 5
- [x] Spec §8 测试（llm/config + admin round-trip + health probe auth）→ Tasks 1, 3, 5
- [x] Spec §9 CLAUDE.md → Task 6
- [x] Spec §10 已知边界（不做项）→ 全文贯彻（无 secret masking、无长度校验、不动 base_url hot-reload）
- [x] 占位符：无 TBD/TODO；所有代码块完整
- [x] 类型一致性：`LLMConfig.api_key: str` 在 Task 1 定义，Task 2/3/5 一致使用；`DEFAULTS["llm"]["api_key"]` 在 Task 4 定义，Task 5 测试引用一致
- [x] 测试 fixture 复用：`client` / `logged_in` 来自 `tests/test_admin_routes.py`（已存在）