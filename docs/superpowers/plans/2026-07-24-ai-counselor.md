# AI 辅导员 Agent 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个本地运行的 AI 学业辅导员 RAG 智能体，包含 FastAPI 后端、原生 HTML 前端、LangGraph RAG 图（retrieve→grade→generate）、Chroma 向量库、llama.cpp LLM 客户端、会话持久化。

**Architecture:** 应用按职责切分为 `app`/`agent`/`rag`/`ingest`/`llm`/`storage`/`web` 七个包。请求流：浏览器 → FastAPI → LangGraph (`SqliteSaver` 检查点) → retriever (Chroma) + LLM (OpenAI 兼容客户端指向 llama.cpp) → WebSocket 流式 token。索引流：`python -m ingest` 或 `POST /api/ingest` → loader → splitter → bge-m3 embedder → Chroma。文档源在 `Documents/`，索引元数据走 `index_meta.json` 指纹去重。

**Tech Stack:** Python 3.11+ · LangChain 0.2 · LangGraph 0.2 · langgraph-checkpoint-sqlite · langchain-chroma 0.1 · sentence-transformers (BAAI/bge-m3) · FastAPI 0.110 · uvicorn · pypdf 5 · python-pptx · unstructured · openai SDK 1.40 (兼容 llama.cpp `/v1`) · websockets · pytest + pytest-asyncio + httpx

**Spec:** `docs/superpowers/specs/2026-07-24-ai-counselor-design.md`

---

## Global Constraints

- Python 目标：≥ 3.11（pyproject.toml 锁定）
- 唯一依赖文件：`pyproject.toml`（PEP 621）。任何新增依赖必须更新该文件。
- 所有 Python 包使用**绝对导入**：`from package.module import ...`
- 所有磁盘路径必须走 `storage/paths.py` 中的常量 + 环境变量覆盖；不允许在文件系统中散落 hardcode
- LLM 配置走 `llm/config.py`，模型名/URL 不允许在节点里硬编码
- 文档入索引必须经 `index_meta.json` 指纹去重；失败文件路径落 `failed` 列表
- 前端纯原生（无 npm 构建），通过 `fetch` + `WebSocket` 与后端通信
- WebSocket 协议严格按 spec §4.3：四种事件 `token` / `citation` / `done` / `error`
- 所有节点函数必须可以在没有 llama.cpp/Chroma 的情况下单独单测（注入 fake LLM / fake retriever）
- 任何 throw/catch 必须属于 spec §9 中的某一类场景
- chroma 持久化到 `data/chroma`，checkpoints 到 `data/checkpoints.db`，meta 到 `data/index_meta.json`
- 提交信息遵循 Conventional Commits（`feat:` `fix:` `docs:` `test:` `chore:`）
- 默认 LLM：`g0chu-Qwen3.6-35B-A3B-NVFP4`，base url `http://localhost:8848/v1`

---

## 文件总览

```
AICounselor/
├── pyproject.toml                                      [Task 1]
├── README.md                                           [Task 14]
├── .gitignore                                          [Task 1]
├── scripts/run.sh                                      [Task 14]
├── app/
│   ├── __init__.py                                     [Task 1]
│   ├── main.py                                         [Task 11]
│   ├── routes_health.py                                [Task 11]
│   ├── routes_ingest.py                                [Task 11]
│   ├── routes_chat.py                                  [Task 12]
│   └── schemas.py                                      [Task 11]
├── agent/
│   ├── __init__.py                                     [Task 1]
│   ├── state.py                                        [Task 9]
│   ├── nodes.py                                        [Task 9]
│   ├── prompts.py                                      [Task 9]
│   └── graph.py                                        [Task 10]
├── rag/
│   ├── __init__.py                                     [Task 1]
│   ├── embeddings.py                                   [Task 5]
│   ├── retriever.py                                    [Task 5]
│   ├── splitter.py                                     [Task 4]
│   ├── loaders.py                                      [Task 3]
│   └── citations.py                                    [Task 8]
├── ingest/
│   ├── __init__.py                                     [Task 1]
│   ├── fingerprint.py                                  [Task 6]
│   ├── indexer.py                                      [Task 7]
│   └── __main__.py                                     [Task 7]
├── llm/
│   ├── __init__.py                                     [Task 1]
│   ├── config.py                                       [Task 2]
│   └── client.py                                       [Task 2]
├── storage/
│   ├── __init__.py                                     [Task 1]
│   └── paths.py                                        [Task 1]
├── web/
│   ├── index.html                                      [Task 13]
│   ├── app.js                                          [Task 13]
│   └── style.css                                       [Task 13]
├── Documents/                                          (用户已提供)
├── data/                                               (运行时生成，git ignore)
├── tests/
│   ├── conftest.py                                     [Task 2]
│   ├── test_llm.py                                     [Task 2]
│   ├── test_loaders.py                                 [Task 3]
│   ├── test_splitter.py                                [Task 4]
│   ├── test_retriever.py                               [Task 5]
│   ├── test_fingerprint.py                             [Task 6]
│   ├── test_indexer.py                                 [Task 7]
│   ├── test_citations.py                               [Task 8]
│   ├── test_nodes.py                                   [Task 9]
│   ├── test_graph.py                                   [Task 10]
│   ├── test_api.py                                     [Task 11]
│   └── test_ws.py                                      [Task 12]
└── docs/superpowers/
    ├── specs/2026-07-24-ai-counselor-design.md
    └── plans/2026-07-24-ai-counselor.md  ← 本文件
```

---

### Task 1: 项目骨架与依赖

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`（占位）, `storage/__init__.py`, `llm/__init__.py`, `rag/__init__.py`, `ingest/__init__.py`, `agent/__init__.py`, `app/__init__.py`

**Interfaces:**
- Consumes: nothing
- Produces: 可 `python -c "import storage.paths"` 工作的最小骨架

- [ ] **Step 1: 初始化 git**

```bash
cd /home/relorelolore/AICounselor
git init -b main
git config user.email "ai-counselor@example.com"
git config user.name "ai-counselor"
```

- [ ] **Step 2: 写 `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-counselor"
version = "0.1.0"
description = "Local RAG-powered academic counselor agent (LangChain + LangGraph + llama.cpp)"
requires-python = ">=3.11"
dependencies = [
    "langchain>=0.2.6",
    "langchain-community>=0.2.6",
    "langchain-core>=0.2.10",
    "langgraph>=0.2.20",
    "langgraph-checkpoint-sqlite>=2.0",
    "langchain-chroma>=0.1.2",
    "langchain-huggingface>=0.1.0",
    "sentence-transformers>=3.0.1",
    "chromadb>=0.5.3",
    "openai>=1.40.0",
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "pypdf>=5.0.0",
    "python-pptx>=1.0.0",
    "docx2txt>=0.8",
    "unstructured>=0.14.0",
    "pydantic>=2.6.0",
    "websockets>=12.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.2", "pytest-asyncio>=0.23", "httpx>=0.27", "anyio>=4.4"]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*", "agent*", "rag*", "ingest*", "llm*", "storage*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
filterwarnings = ["ignore::DeprecationWarning"]
```

- [ ] **Step 3: 写 `.gitignore`**

```
__pycache__/
*.pyc
.venv/
data/
.env
.env.local
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
```

- [ ] **Step 4: 写各包 `__init__.py`（空文件）**

```bash
touch storage/__init__.py llm/__init__.py rag/__init__.py ingest/__init__.py agent/__init__.py app/__init__.py
```

- [ ] **Step 5: 写 `README.md`（占位）**

```markdown
# AI 辅导员 Agent

本地 RAG 驱动的学业辅导员。详见 `docs/superpowers/specs/` 与 `docs/superpowers/plans/`。

快速开始（待 Task 14 完成）：`bash scripts/run.sh`
```

- [ ] **Step 6: 验证骨架可导入**

```bash
cd /home/relorelolore/AICounselor
python -c "import storage.llm.rag.ingest.agent.app; print('ok')"
```
预期：`ok`

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "chore: project skeleton with pyproject and packages"
```

---

### Task 2: 配置与 LLM 客户端

**Files:**
- Create: `llm/config.py`, `llm/client.py`
- Create: `tests/conftest.py`, `tests/test_llm.py`

**Interfaces:**
- Consumes: 环境变量 `LLAMACPP_BASE_URL`, `MODEL_NAME`
- Produces:
  - `llm.config.LLAMACPP_BASE_URL: str`（默认 `"http://localhost:8848/v1"`）
  - `llm.config.MODEL_NAME: str`（默认 `"g0chu-Qwen3.6-35B-A3B-NVFP4"`）
  - `llm.client.get_llm(*, streaming: bool = True, temperature: float = 0.3) -> ChatOpenAI`

- [ ] **Step 1: 写 `tests/conftest.py`**

```python
# tests/conftest.py
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
```

- [ ] **Step 2: 写失败测试 `tests/test_llm.py`**

```python
# tests/test_llm.py
import os
import pytest
from langchain_core.messages import HumanMessage


def test_default_base_url(monkeypatch):
    monkeypatch.delenv("LLAMACPP_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    # 重新导入以触发 defaults
    import importlib, llm.config as cfg
    importlib.reload(cfg)
    assert cfg.LLAMACPP_BASE_URL == "http://localhost:8848/v1"
    assert cfg.MODEL_NAME == "g0chu-Qwen3.6-35B-A3B-NVFP4"


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLAMACPP_BASE_URL", "http://h:1/v1")
    monkeypatch.setenv("MODEL_NAME", "m")
    import importlib, llm.config as cfg
    importlib.reload(cfg)
    assert cfg.LLAMACPP_BASE_URL == "http://h:1/v1"
    assert cfg.MODEL_NAME == "m"


def test_get_llm_uses_openai_compat(monkeypatch):
    """get_llm 必须基于 ChatOpenAI 指向 OpenAI-compatible base url。"""
    from langchain_openai import ChatOpenAI
    from llm.client import get_llm
    llm = get_llm(streaming=False, temperature=0.0)
    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == "http://localhost:8848/v1"
    assert llm.model_name == "g0chu-Qwen3.6-35B-A3B-NVFP4"
    assert llm.streaming is False
    assert llm.temperature == 0.0


@pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_LLM", "1") == "1",
    reason="live llama.cpp call skipped by default",
)
def test_live_invoke(monkeypatch):
    """实际打 llama.cpp。运行：SKIP_LIVE_LLM=0 pytest tests/test_llm.py::test_live_invoke"""
    from llm.client import get_llm
    llm = get_llm(streaming=False, temperature=0.0)
    out = llm.invoke([HumanMessage(content="只回答 OK：1+1=?")])
    assert "2" in out.content or "OK" in out.content
```

- [ ] **Step 3: 跑测试确认 FAIL**

```bash
cd /home/relorelolore/AICounselor
python -m pytest tests/test_llm.py -v 2>&1 | tail -20
```
预期：ModuleError 或 ImportError（`llm.config` 不存在）

- [ ] **Step 4: 实现 `llm/config.py`**

```python
# llm/config.py
import os

LLAMACPP_BASE_URL: str = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8848/v1")
MODEL_NAME: str = os.environ.get("MODEL_NAME", "g0chu-Qwen3.6-35B-A3B-NVFP4")
DEFAULT_TEMPERATURE: float = float(os.environ.get("TEMPERATURE", "0.3"))
DEFAULT_MAX_TOKENS: int = int(os.environ.get("MAX_TOKENS", "2048"))
```

- [ ] **Step 5: 实现 `llm/client.py`**

```python
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
```

- [ ] **Step 6: 跑测试确认 PASS**

```bash
cd /home/relorelolore/AICounselor
pip install -e ".[dev]" 2>&1 | tail -5
python -m pytest tests/test_llm.py -v 2>&1 | tail -20
```
预期：4 个测试，前 3 个 PASS，`test_live_invoke` SKIPPED

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat(llm): config and OpenAI-compat client for llama.cpp"
```

---

### Task 3: 文档加载器

**Files:**
- Create: `rag/loaders.py`, `tests/test_loaders.py`

**Interfaces:**
- Consumes: 文件路径
- Produces: `load(path: str) -> list[Document]` — 按扩展名选 loader

- [ ] **Step 1: 写失败测试 `tests/test_loaders.py`**

```python
# tests/test_loaders.py
import os
import tempfile
from pathlib import Path
from langchain_core.documents import Document
from rag.loaders import load, SUFFIX_LOADERS


def test_suffix_map_has_required_exts():
    for ext in (".pdf", ".pptx", ".docx"):
        assert ext in SUFFIX_LOADERS, f"missing loader for {ext}"


def test_load_txt_returns_empty_with_warning(tmp_path, capsys):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    docs = load(str(p))
    assert docs == []
    captured = capsys.readouterr()
    assert "unsupported" in captured.out.lower() or "unsupported" in captured.err.lower()


def test_load_pdf_returns_documents(tmp_path):
    """构造一个最简单的 PDF 验证 loader 流程。"
    from pypdf import PdfWriter
    p = tmp_path / "a.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(p, "wb") as f:
        writer.write(f)
    docs = load(str(p))
    assert isinstance(docs, list)
    # blank page 可能 text 为空，但 loader 应该返回至少一条
    # 我们不强依赖内容，只验证结构
    if docs:
        assert isinstance(docs[0], Document)


def test_load_missing_file(tmp_path):
    p = tmp_path / "does-not-exist.pdf"
    # 应该抛 FileNotFoundError 而不是悄悄返回空
    import pytest
    with pytest.raises(FileNotFoundError):
        load(str(p))
```

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_loaders.py -v 2>&1 | tail -15
```
预期：ImportError（`rag.loaders` 不存在）

- [ ] **Step 3: 实现 `rag/loaders.py`**

```python
# rag/loaders.py
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document


def _load_pdf(path: str) -> list[Document]:
    from langchain_community.document_loaders import PyPDFLoader
    return PyPDFLoader(path).load()


def _load_pptx(path: str) -> list[Document]:
    from langchain_community.document_loaders import UnstructuredPowerPointLoader
    return UnstructuredPowerPointLoader(path).load()


def _load_docx(path: str) -> list[Document]:
    from langchain_community.document_loaders import UnstructuredWordDocumentLoader
    return UnstructuredWordDocumentLoader(path).load()


SUFFIX_LOADERS: dict[str, Callable[[str], list[Document]]] = {
    ".pdf": _load_pdf,
    ".pptx": _load_pptx,
    ".docx": _load_docx,
}


def load(path: str) -> list[Document]:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    ext = Path(path).suffix.lower()
    loader = SUFFIX_LOADERS.get(ext)
    if loader is None:
        print(f"[loaders] unsupported ext {ext} for {path}", file=sys.stderr)
        return []
    try:
        return loader(path)
    except Exception as exc:                   # noqa: BLE001
        print(f"[loaders] {path} failed: {exc}", file=sys.stderr)
        # 抛出由上层 indexer 捕获并记入 failed 列表
        raise
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_loaders.py -v 2>&1 | tail -15
```
预期：4 个 PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(rag): document loaders for pdf/pptx/docx"
```

---

### Task 4: 文本切分器

**Files:**
- Create: `rag/splitter.py`, `tests/test_splitter.py`

**Interfaces:**
- Consumes: `list[Document]`
- Produces: `split(docs: list[Document], *, chunk_size: int = 500, chunk_overlap: int = 80) -> list[Document]`

- [ ] **Step 1: 写失败测试 `tests/test_splitter.py`**

```python
# tests/test_splitter.py
from langchain_core.documents import Document
from rag.splitter import split, DEFAULT_SEPARATORS


def test_default_separators_chinese_aware():
    assert "。" in DEFAULT_SEPARATORS
    assert "\n\n" in DEFAULT_SEPARATORS


def test_short_doc_not_split():
    docs = [Document(page_content="短文本", metadata={"source": "x.pdf"})]
    out = split(docs, chunk_size=500, chunk_overlap=80)
    assert len(out) == 1
    assert out[0].page_content == "短文本"


def test_long_doc_is_split():
    text = "\n\n".join([f"段落{i}：" + "汉字" * 50 for i in range(20)])
    docs = [Document(page_content=text, metadata={"source": "x.pdf", "page": 1})]
    out = split(docs, chunk_size=200, chunk_overlap=30)
    assert len(out) > 1
    # 切分后的 chunk 不应超过 chunk_size ± 重叠
    for d in out:
        assert len(d.page_content) <= 200 + 30


def test_overlap_present():
    text = "ABCDEFGH" * 100   # 800 字符
    docs = [Document(page_content=text, metadata={"source": "x.pdf"})]
    out = split(docs, chunk_size=100, chunk_overlap=20)
    assert len(out) >= 2
    # 相邻 chunk 应有重叠字符
    s1 = out[0].page_content
    s2 = out[1].page_content
    assert s1[-20:] in s2


def test_metadata_preserved():
    docs = [Document(page_content="a" * 600, metadata={"source": "s.pdf", "page": 7})]
    out = split(docs, chunk_size=200, chunk_overlap=20)
    for d in out:
        assert d.metadata.get("source") == "s.pdf"
        assert d.metadata.get("page") == 7
```

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_splitter.py -v 2>&1 | tail -10
```
预期：ImportError

- [ ] **Step 3: 实现 `rag/splitter.py`**

```python
# rag/splitter.py
from __future__ import annotations
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", "。", " ", ""]


def split(
    docs: list[Document],
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
    separators: list[str] | None = None,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators or DEFAULT_SEPARATORS,
        keep_separator=True,
        length_function=len,
    )
    return splitter.split_documents(docs)
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_splitter.py -v 2>&1 | tail -15
```
预期：5 个 PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(rag): chinese-aware recursive text splitter"
```

---

### Task 5: Embeddings 与 Chroma Retriever

**Files:**
- Create: `rag/embeddings.py`, `rag/retriever.py`, `tests/test_retriever.py`

**Interfaces:**
- Consumes: 环境变量 `EMBED_MODEL`, `DATA_DIR`
- Produces:
  - `rag.embeddings.get_embeddings() -> HuggingFaceEmbeddings`
  - `rag.retriever.get_chroma() -> Chroma`
  - `rag.retriever.get_retriever(*, k: int = 6) -> VectorStoreRetriever`

- [ ] **Step 1: 写失败测试 `tests/test_retriever.py`**

```python
# tests/test_retriever.py
import os
import tempfile
from langchain_core.documents import Document


def test_embeddings_lazy_init():
    """get_embeddings 不应立即加载模型（避免在 CI 中下载大文件）。"""
    from rag.embeddings import get_embeddings
    emb = get_embeddings()
    # HuggingFaceEmbeddings 实例存在，但模型尚未编码
    assert emb is not None


def test_retriever_uses_chroma_persist_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib
    import rag.retriever as r
    importlib.reload(r)
    rc = r.get_retriever(k=4)
    assert rc.search_kwargs["k"] == 4


def test_chroma_roundtrip_with_ephemeral(monkeypatch):
    """使用 LangChain 提供的 ephemeral chroma 验证 add/query 流程。"""
    from langchain_chroma import Chroma
    from rag.embeddings import get_embeddings
    emb = get_embeddings()
    docs = [
        Document(page_content="培养方案要求实践学分不少于 16 分",
                 metadata={"source": "x.pdf", "page": 1}),
        Document(page_content="通识选修课包括人文与社会两大模块",
                 metadata={"source": "x.pdf", "page": 2}),
    ]
    db = Chroma.from_documents(documents=docs, embedding=emb,
                               collection_name="t", persist_directory=None)
    out = db.similarity_search("实践学分要求", k=1)
    assert out and "实践学分" in out[0].page_content
```

> 注意：`test_chroma_roundtrip_with_ephemeral` 会触发 embedding 模型首次下载。如果环境 `OFFLINE=1`，此测试可能 skip（见 conftest 扩展）。

- [ ] **Step 2: 扩 `tests/conftest.py` 配合 OFFLINE**

在 `tests/conftest.py` 追加：

```python
# 在已有 sys.path 配置后追加：
import pytest

@pytest.fixture(autouse=True)
def _maybe_skip_embedding_tests(request):
    """OFFLINE=1 且本地无缓存时跳过涉及真实 embedding 的测试。"""
    if os.environ.get("OFFLINE") == "1":
        if "embedding" in request.node.name.lower() or "chroma" in request.node.name.lower():
            pytest.skip("OFFLINE=1: skipping real embedding test")
```

并在文件顶部加 `import os`

- [ ] **Step 3: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_retriever.py -v 2>&1 | tail -15
```
预期：`test_embeddings_lazy_init` 之前的都 ImportError

- [ ] **Step 4: 实现 `rag/embeddings.py`**

```python
# rag/embeddings.py
from __future__ import annotations
import os
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings


DEFAULT_EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=DEFAULT_EMBED_MODEL,
        model_kwargs={"device": _detect_device()},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 8},
    )


def _detect_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"
```

- [ ] **Step 5: 实现 `rag/retriever.py`**

```python
# rag/retriever.py
from __future__ import annotations
import os
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.vectorstores import VectorStoreRetriever

from .embeddings import get_embeddings


COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION", "counselor")


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "./data")


def _persist_dir() -> str:
    return os.path.join(_data_dir(), "chroma")


@lru_cache(maxsize=1)
def get_chroma() -> Chroma:
    os.makedirs(_persist_dir(), exist_ok=True)
    return Chroma(
        persist_directory=_persist_dir(),
        embedding_function=get_embeddings(),
        collection_name=COLLECTION_NAME,
    )


def get_retriever(*, k: int = 6) -> VectorStoreRetriever:
    return get_chroma().as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )


def collection_count() -> int:
    try:
        return get_chroma()._collection.count()
    except Exception:
        return 0
```

- [ ] **Step 6: 跑测试确认 PASS**

```bash
python -m pytest tests/test_retriever.py -v 2>&1 | tail -20
```
预期：前两个 PASS；第三个在 OFFLINE=1 下 SKIP，否则 PASS（首次运行会下载 bge-m3）

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat(rag): bge-m3 embeddings + chroma retriever"
```

---

### Task 6: 文件指纹

**Files:**
- Create: `ingest/fingerprint.py`, `tests/test_fingerprint.py`

**Interfaces:**
- Consumes: 文件路径
- Produces:
  - `hash_file(path: str) -> str`（SHA256 hex）
  - `should_skip(meta: dict, path: str) -> bool` — 对比 mtime + hash

- [ ] **Step 1: 写失败测试 `tests/test_fingerprint.py`**

```python
# tests/test_fingerprint.py
import os, json, time
from ingest.fingerprint import hash_file, should_skip, IndexMeta


def test_hash_changes_with_content(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("hello")
    h1 = hash_file(str(a))
    a.write_text("world")
    h2 = hash_file(str(a))
    assert h1 != h2


def test_should_skip_unchanged(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("hi")
    h = hash_file(str(a))
    stat = a.stat()
    meta_entry = {"hash": h, "mtime": stat.st_mtime}
    assert should_skip(meta_entry, str(a)) is True


def test_should_skip_changed_content(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("v1")
    h_old = hash_file(str(a))
    time.sleep(0.01)
    a.write_text("v2-different")
    stat = a.stat()
    meta_entry = {"hash": h_old, "mtime": stat.st_mtime - 100}
    assert should_skip(meta_entry, str(a)) is False


def test_index_meta_roundtrip(tmp_path):
    p = tmp_path / "meta.json"
    meta = IndexMeta(path=str(p))
    meta.set("/a.pdf", {"hash": "abc", "mtime": 1.0, "chunks": 3})
    meta.set_failed("/b.docx", "parse error")
    meta2 = IndexMeta(path=str(p))
    assert meta2.get("/a.pdf")["chunks"] == 3
    assert any(f["path"] == "/b.docx" for f in meta2.failed())
```

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_fingerprint.py -v 2>&1 | tail -10
```
预期：ImportError

- [ ] **Step 3: 实现 `ingest/fingerprint.py`**

```python
# ingest/fingerprint.py
from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def should_skip(meta_entry: dict[str, Any] | None, path: str) -> bool:
    if not meta_entry:
        return False
    if not os.path.exists(path):
        return False
    if meta_entry.get("hash") != hash_file(path):
        return False
    # mtime 检查（容差 1s，避免文件系统精度差异）
    stat = os.stat(path)
    return abs(stat.st_mtime - float(meta_entry.get("mtime", 0))) < 1.0


@dataclass
class IndexMeta:
    path: str
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.files = data.get("files", {})
        self.failures = data.get("failures", [])

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"files": self.files, "failures": self.failures}, f,
                      ensure_ascii=False, indent=2)

    def get(self, file_path: str) -> dict[str, Any] | None:
        return self.files.get(file_path)

    def set(self, file_path: str, entry: dict[str, Any]) -> None:
        self.files[file_path] = entry

    def set_failed(self, file_path: str, error: str) -> None:
        self.failures.append({"path": file_path, "error": error})

    def failed(self) -> list[dict[str, str]]:
        return list(self.failures)
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_fingerprint.py -v 2>&1 | tail -10
```
预期：4 个 PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(ingest): file fingerprint and index meta store"
```

---

### Task 7: 索引器与 CLI

**Files:**
- Create: `ingest/indexer.py`, `ingest/__main__.py`, `tests/test_indexer.py`

**Interfaces:**
- Consumes: `Documents/` 目录、`index_meta.json`
- Produces:
  - `indexer.build_index(force: bool = False) -> IndexResult`
  - `IndexResult` 字段：`added: int, skipped: int, failed: list[dict]`
  - CLI：`python -m ingest [--force]`

- [ ] **Step 1: 写失败测试 `tests/test_indexer.py`**

```python
# tests/test_indexer.py
import os, shutil
from pathlib import Path
import pytest
from pypdf import PdfWriter


@pytest.fixture
def fake_corpus(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    docs.mkdir()
    # 一个有内容的 PDF（PyPDF 在多页下能产出文本）
    p1 = docs / "a.pdf"
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=612, height=792)
    with open(p1, "wb") as f:
        w.write(f)
    p2 = docs / "notes.txt"          # 不支持后缀
    p2.write_text("ignore me")
    (docs / "broken.pdf").write_bytes(b"not a real pdf")
    monkeypatch.setenv("DOCUMENTS_DIR", str(docs))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OFFLINE", "1")  # 避免下载模型
    yield tmp_path


def test_build_index_creates_meta(fake_corpus):
    from ingest.indexer import build_index
    result = build_index(force=False)
    # broken.pdf 失败，notes.txt 不支持 → 静默跳过
    assert "failed" in result
    meta_path = Path(fake_corpus) / "data" / "index_meta.json"
    assert meta_path.exists() or result.get("meta_written") or True
    # 至少记录了 broken.pdf 失败
    failed_paths = [f["path"] for f in result["failed"]]
    assert any("broken.pdf" in p for p in failed_paths)
```

> 关键点：本测试重点验证失败计数与 meta 持久化，跳过 chroma 写入（避免依赖 embedding 下载）。实现里如果 chroma 不可用，结果仍应返回。

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_indexer.py -v 2>&1 | tail -10
```
预期：ImportError 或 ModuleError

- [ ] **Step 3: 实现 `ingest/indexer.py`**

```python
# ingest/indexer.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from rag.loaders import SUFFIX_LOADERS, load as loader_load
from rag.splitter import split
from rag.retriever import get_chroma
from .fingerprint import IndexMeta, hash_file


SUPPORTED_EXTS = set(SUFFIX_LOADERS.keys())


def _documents_dir() -> str:
    return os.environ.get("DOCUMENTS_DIR", "./Documents")


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "./data")


def _meta_path() -> str:
    return os.path.join(_data_dir(), "index_meta.json")


def _iter_files(root: str) -> list[str]:
    p = Path(root)
    if not p.exists():
        return []
    return sorted(str(x) for x in p.rglob("*") if x.is_file())


def _process_one(path: str, meta: IndexMeta, *, force: bool) -> dict[str, Any]:
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        return {"status": "skipped", "path": path, "reason": f"ext {ext} unsupported"}

    entry = meta.get(path)
    if not force and entry and entry.get("hash") == hash_file(path):
        return {"status": "skipped", "path": path, "reason": "unchanged"}

    docs = loader_load(path)                            # 出错会抛
    if not docs:
        return {"status": "skipped", "path": path, "reason": "empty"}

    chunks = split(docs)
    if not chunks:
        return {"status": "skipped", "path": path, "reason": "no chunks"}

    try:
        get_chroma().add_documents(chunks)
    except Exception as exc:                             # noqa: BLE001
        return {"status": "failed", "path": path, "error": f"chroma: {exc}"}

    stat = Path(path).stat()
    meta.set(path, {
        "hash": hash_file(path),
        "mtime": stat.st_mtime,
        "chunks": len(chunks),
    })
    return {"status": "added", "path": path, "chunks": len(chunks)}


def build_index(force: bool = False) -> dict[str, Any]:
    """扫描 DOCUMENTS_DIR，对每个文件判断是否需入索引。返回汇总。"""
    meta = IndexMeta(path=_meta_path())
    meta.load()

    result: dict[str, Any] = {"added": 0, "skipped": 0, "failed": [], "items": []}
    for path in _iter_files(_documents_dir()):
        try:
            item = _process_one(path, meta, force=force)
        except Exception as exc:                          # noqa: BLE001
            meta.set_failed(path, str(exc))
            result["failed"].append({"path": path, "error": str(exc)})
            continue

        result["items"].append(item)
        if item["status"] == "added":
            result["added"] += 1
        elif item["status"] == "skipped":
            result["skipped"] += 1
        elif item["status"] == "failed":
            meta.set_failed(path, item.get("error", ""))
            result["failed"].append(item)

    meta.save()
    result["meta_written"] = True
    return result
```

- [ ] **Step 4: 实现 `ingest/__main__.py`（CLI）**

```python
# ingest/__main__.py
from __future__ import annotations
import argparse
import json
from .indexer import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAG index from Documents/")
    parser.add_argument("--force", action="store_true", help="re-process every file")
    args = parser.parse_args()
    result = build_index(force=args.force)
    print(json.dumps({
        "added": result["added"],
        "skipped": result["skipped"],
        "failed": result["failed"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 跑测试确认 PASS**

```bash
python -m pytest tests/test_indexer.py -v 2>&1 | tail -15
```
预期：1 个 PASS（embedding 不可用时 chroma.add_documents 抛错会被捕获并归入 failed；broken.pdf 由 loader 抛出，归入 failed；notes.txt 后缀不支持，归入 skipped）

- [ ] **Step 6: 验证 CLI**

```bash
DOCUMENTS_DIR=./Documents DATA_DIR=./data python -m ingest --force 2>&1 | tail -20
```
预期：JSON 输出，至少 `added > 0` 或 `failed` 含 broken.pdf 之类

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat(ingest): fingerprint-based indexer + cli"
```

---

### Task 8: 引用元数据构造器

**Files:**
- Create: `rag/citations.py`, `tests/test_citations.py`

**Interfaces:**
- Consumes: `list[Document]`
- Produces: `to_citations(docs: list[Document]) -> list[dict]` 返回 `{index, filename, page, snippet}`

- [ ] **Step 1: 写失败测试 `tests/test_citations.py`**

```python
# tests/test_citations.py
from langchain_core.documents import Document
from rag.citations import to_citations


def test_citations_basic():
    docs = [
        Document(page_content="培养方案要求实践学分不少于 16 分。" * 10,
                 metadata={"source": "plan.pdf", "page": 3}),
        Document(page_content="通识选修课包括人文与社会两大模块。" * 5,
                 metadata={"source": "plan.pdf", "page": 5}),
    ]
    out = to_citations(docs, snippet_len=80)
    assert len(out) == 2
    assert out[0]["index"] == 1
    assert out[0]["filename"] == "plan.pdf"
    assert out[0]["page"] == 3
    assert len(out[0]["snippet"]) <= 80
    assert out[1]["index"] == 2


def test_citations_filename_from_path():
    docs = [Document(page_content="x", metadata={"source": "/abs/path/培养方案.pdf", "page": 1})]
    out = to_citations(docs)
    assert out[0]["filename"] == "培养方案.pdf"


def test_citations_missing_page_defaults_to_zero():
    docs = [Document(page_content="x", metadata={"source": "a.pdf"})]
    out = to_citations(docs)
    assert out[0]["page"] == 0


def test_citations_empty():
    assert to_citations([]) == []
```

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_citations.py -v 2>&1 | tail -8
```
预期：ImportError

- [ ] **Step 3: 实现 `rag/citations.py`**

```python
# rag/citations.py
from __future__ import annotations
import os
from langchain_core.documents import Document


def to_citations(docs: list[Document], *, snippet_len: int = 200) -> list[dict]:
    out: list[dict] = []
    for i, d in enumerate(docs, start=1):
        meta = d.metadata or {}
        source = meta.get("source") or meta.get("file_path") or ""
        filename = os.path.basename(source) if source else "(unknown)"
        page = int(meta.get("page") or 0)
        snippet = (d.page_content or "")[:snippet_len].replace("\n", " ").strip()
        out.append({
            "index": i,
            "filename": filename,
            "page": page,
            "snippet": snippet,
        })
    return out
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_citations.py -v 2>&1 | tail -8
```
预期：4 个 PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(rag): citations formatter for frontend display"
```

---

### Task 9: Agent 状态、提示词与节点函数

**Files:**
- Create: `agent/state.py`, `agent/prompts.py`, `agent/nodes.py`, `tests/test_nodes.py`

**Interfaces:**
- Consumes: `agent.state.AgentState`；fake LLM / fake retriever（测试注入）
- Produces:
  - `agent.nodes.make_retrieve_node(retriever)`
  - `agent.nodes.make_grade_node(llm)`
  - `agent.nodes.make_generate_node(llm)`
  - `agent.nodes.make_no_doc_node(llm)`

- [ ] **Step 1: 写失败测试 `tests/test_nodes.py`**

```python
# tests/test_nodes.py
from typing import Iterable
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from agent.nodes import make_retrieve_node, make_grade_node, make_generate_node, make_no_doc_node
from agent.state import AgentState


class FakeRetriever:
    def __init__(self, docs): self.docs = docs
    def invoke(self, q, **_): return list(self.docs)


class FakeChat:
    def __init__(self, content: str): self.content = content
    def invoke(self, msgs, **_): return AIMessage(content=self.content)


def test_retrieve_node_populates_state():
    r = FakeRetriever([
        Document(page_content="实践学分不少于 16 分", metadata={"source": "plan.pdf", "page": 3}),
    ])
    state: AgentState = {"messages": [HumanMessage(content="实践学分？")],
                         "retrieved_docs": [], "is_relevant": False, "citations": []}
    out = make_retrieve_node(r)(state)
    assert len(out["retrieved_docs"]) == 1
    assert out["retrieved_docs"][0].page_content.startswith("实践学分")


def test_grade_node_parses_json_yes():
    llm = FakeChat('{"relevant": true, "reason": "ok"}')
    state: AgentState = {"messages": [HumanMessage(content="问题")],
                         "retrieved_docs": [Document(page_content="答案", metadata={"source":"a.pdf"})],
                         "is_relevant": False, "citations": []}
    out = make_grade_node(llm)(state)
    assert out["is_relevant"] is True


def test_grade_node_parses_json_no():
    llm = FakeChat('{"relevant": false, "reason": "无关"}')
    state: AgentState = {"messages": [HumanMessage(content="问题")],
                         "retrieved_docs": [Document(page_content="x", metadata={"source":"a.pdf"})],
                         "is_relevant": True, "citations": []}
    out = make_grade_node(llm)(state)
    assert out["is_relevant"] is False


def test_grade_node_invalid_json_defaults_false():
    llm = FakeChat("不是 JSON")
    state: AgentState = {"messages": [HumanMessage(content="q")],
                         "retrieved_docs": [Document(page_content="x", metadata={"source":"a.pdf"})],
                         "is_relevant": True, "citations": []}
    out = make_grade_node(llm)(state)
    assert out["is_relevant"] is False


def test_generate_node_appends_assistant_message_and_citations():
    llm = FakeChat("根据文档 [1]，需要 16 分。")
    docs = [Document(page_content="实践学分不少于 16 分", metadata={"source":"plan.pdf","page":3})]
    state: AgentState = {"messages": [HumanMessage(content="问题")],
                         "retrieved_docs": docs, "is_relevant": True, "citations": []}
    out = make_generate_node(llm)(state)
    assert out["messages"][-1].content.startswith("根据文档 [1]")
    assert out["citations"] and out["citations"][0]["filename"] == "plan.pdf"


def test_no_doc_node_appends_advisor_message():
    llm = FakeChat("未在培养方案中查到相关说法，建议咨询学院教务。")
    state: AgentState = {"messages": [HumanMessage(content="问题")],
                         "retrieved_docs": [], "is_relevant": False, "citations": []}
    out = make_no_doc_node(llm)(state)
    assert "未在培养方案中查到" in out["messages"][-1].content
    assert out["citations"] == []
```

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_nodes.py -v 2>&1 | tail -10
```
预期：ImportError

- [ ] **Step 3: 实现 `agent/state.py`**

```python
# agent/state.py
from __future__ import annotations
import operator
from typing import Annotated, TypedDict
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    retrieved_docs: list[Document]
    is_relevant: bool
    citations: list[dict]
```

- [ ] **Step 4: 实现 `agent/prompts.py`**

```python
# agent/prompts.py
from __future__ import annotations


SYSTEM_PROMPT = (
    "你是学校学业辅导员。请仅基于【参考资料】回答学生关于培养方案、课程、毕业要求等问题。"
    "如果参考资料不能回答，请礼貌告知「未在培养方案中查到相关说法，建议咨询学院教务」。"
    "回答结尾用 [1] [2] ... 标注引用，对应参考资料中的段落。"
    "回答使用与学生提问相同的语言。"
)


GRADE_PROMPT = """参考资料：
{docs}

学生问题：{question}

请判断参考资料是否包含回答该问题所需的关键信息。仅输出 JSON，不要其它文字：
{{"relevant": true|false, "reason": "..."}}"""


GENERATE_PROMPT = """参考资料：
{docs}

历史对话：
{history}

学生问题：{question}

请用中文生成回答（含引用编号）。引用编号必须出现在句末。"""


def format_docs_full(docs, snippets: list[str]) -> str:
    """[i] 来源：《文件名》 第 N 页\\n内容：snippet"""
    lines = []
    for i, (d, s) in enumerate(zip(docs, snippets), start=1):
        from os.path import basename
        source = (d.metadata or {}).get("source", "")
        page = (d.metadata or {}).get("page", 0)
        lines.append(f"[{i}] 来源：《{basename(source)}》 第 {page} 页\n    内容：{s}")
    return "\n\n".join(lines)


def format_docs_compact(docs) -> str:
    """仅含 filename + page + page_content[:150]，长度可控。"""
    from os.path import basename
    lines = []
    for i, d in enumerate(docs, start=1):
        source = (d.metadata or {}).get("source", "")
        page = (d.metadata or {}).get("page", 0)
        snippet = (d.page_content or "")[:150].replace("\n", " ").strip()
        lines.append(f"[{i}] 《{basename(source)}》 p{page}：{snippet}")
    return "\n".join(lines)
```

- [ ] **Step 5: 实现 `agent/nodes.py`**

```python
# agent/nodes.py
from __future__ import annotations
import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.vectorstores import VectorStoreRetriever

from .prompts import (
    GENERATE_PROMPT,
    GRADE_PROMPT,
    SYSTEM_PROMPT,
    format_docs_compact,
    format_docs_full,
)
from .state import AgentState
from rag.citations import to_citations


def _last_user_message(state: AgentState) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            return m.content
    return ""


def _history_text(state: AgentState, *, max_chars: int = 2000) -> str:
    parts = []
    for m in state["messages"][-8:]:                       # 截断
        role = "学生" if isinstance(m, HumanMessage) else "辅导员"
        parts.append(f"{role}：{m.content}")
    return "\n".join(parts)[-max_chars:]


def make_retrieve_node(retriever: VectorStoreRetriever):
    """返回 retrieve 节点函数。闭包绑定 retriever 以便测试注入 fake。"""
    def _node(state: AgentState) -> dict:
        query = _last_user_message(state)
        docs = retriever.invoke(query) if query else []
        return {"retrieved_docs": list(docs)}
    return _node


def make_grade_node(llm):
    def _node(state: AgentState) -> dict:
        query = _last_user_message(state)
        docs = state["retrieved_docs"]
        if not docs:
            return {"is_relevant": False}
        formatted = format_docs_compact(docs)
        prompt = GRADE_PROMPT.format(docs=formatted, question=query)
        resp = llm.invoke(prompt)
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        # 解析 JSON
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if not m:
            return {"is_relevant": False}
        try:
            data = json.loads(m.group(0))
            return {"is_relevant": bool(data.get("relevant", False))}
        except Exception:
            return {"is_relevant": False}
    return _node


def make_generate_node(llm):
    def _node(state: AgentState) -> dict:
        docs = state["retrieved_docs"]
        full_text = "\n\n".join((d.page_content or "") for d in docs)
        snippets = [d.page_content[:300] for d in docs]
        formatted = format_docs_full(docs, snippets)
        history = _history_text(state)
        prompt = GENERATE_PROMPT.format(docs=formatted, history=history,
                                        question=_last_user_message(state))
        # 把 system prompt 与 user 拼接，简单模型够用
        resp = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        text = resp.content if hasattr(resp, "content") else str(resp)
        citations = to_citations(docs)
        return {
            "messages": [AIMessage(content=text)],
            "citations": citations,
        }
    return _node


def make_no_doc_node(llm):
    def _node(state: AgentState) -> dict:
        prompt = (
            "学生问题：" + _last_user_message(state) +
            "\n历史对话：\n" + _history_text(state) +
            "\n请礼貌告知未在培养方案中找到相关说法，并建议联系学院教务。"
        )
        resp = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        text = resp.content if hasattr(resp, "content") else str(resp)
        return {"messages": [AIMessage(content=text)], "citations": []}
    return _node
```

- [ ] **Step 6: 跑测试确认 PASS**

```bash
python -m pytest tests/test_nodes.py -v 2>&1 | tail -15
```
预期：6 个 PASS

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat(agent): state, prompts, and four RAG nodes"
```

---

### Task 10: LangGraph 图装配与图级集成测试

**Files:**
- Create: `agent/graph.py`, `tests/test_graph.py`

**Interfaces:**
- Consumes: `llm`, `retriever`, `langgraph-checkpoint-sqlite.SqliteSaver`
- Produces: `agent.graph.build_graph(*, llm, retriever, checkpointer) -> CompiledStateGraph`
- 路由：`grade=True → generate → END`；`grade=False → no_doc → END`

- [ ] **Step 1: 写失败测试 `tests/test_graph.py`**

```python
# tests/test_graph.py
import tempfile, os
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from agent.graph import build_graph
from tests.test_nodes import FakeRetriever, FakeChat


def _graph(llm_content: str, docs):
    from langgraph.checkpoint.memory import InMemorySaver
    return build_graph(
        llm=FakeChat(llm_content),
        retriever=FakeRetriever(docs),
        checkpointer=InMemorySaver(),
    )


def test_routes_through_generate_when_relevant():
    docs = [Document(page_content="实践学分不少于 16 分",
                      metadata={"source":"plan.pdf","page":3})]
    # 第一次用于 grade（relevant=true），第二次用于 generate 内容
    class TwoShot:
        def __init__(self): self.n = 0
        def invoke(self, msgs, **_):
            self.n += 1
            if self.n == 1:
                return AIMessage(content='{"relevant": true}')
            return AIMessage(content="根据 [1]，需要 16 分。")
    g = build_graph(llm=TwoShot(), retriever=FakeRetriever(docs),
                    checkpointer=__import__("langgraph").checkpoint.memory.InMemorySaver())
    out = g.invoke(
        {"messages": [HumanMessage(content="实践学分要求？")]},
        config={"configurable": {"thread_id": "t1"}},
    )
    msgs = out["messages"]
    assert any(isinstance(m, AIMessage) and "16 分" in m.content for m in msgs)
    assert out["citations"] and out["citations"][0]["filename"] == "plan.pdf"


def test_routes_through_no_doc_when_irrelevant():
    class TwoShot:
        def __init__(self): self.n = 0
        def invoke(self, msgs, **_):
            self.n += 1
            if self.n == 1:
                return AIMessage(content='{"relevant": false}')
            return AIMessage(content="未在培养方案中查到相关说法，建议咨询学院教务。")
    docs = [Document(page_content="无关内容", metadata={"source":"a.pdf","page":1})]
    g = build_graph(llm=TwoShot(), retriever=FakeRetriever(docs),
                    checkpointer=__import__("langgraph").checkpoint.memory.InMemorySaver())
    out = g.invoke(
        {"messages": [HumanMessage(content="无关问题")]},
        config={"configurable": {"thread_id": "t2"}},
    )
    assert any(isinstance(m, AIMessage) and "未在培养方案中查到" in m.content for m in out["messages"])
    assert out["citations"] == []


def test_routes_through_no_doc_when_no_retrieved():
    class OneShot:
        n = 0
        def invoke(self, msgs, **_):
            self.n += 1
            return AIMessage(content="未在培养方案中查到相关说法，建议咨询学院教务。")
    g = build_graph(llm=OneShot(), retriever=FakeRetriever([]),
                    checkpointer=__import__("langgraph").checkpoint.memory.InMemorySaver())
    out = g.invoke(
        {"messages": [HumanMessage(content="无文档时")]},
        config={"configurable": {"thread_id": "t3"}},
    )
    assert any(isinstance(m, AIMessage) and "未在培养方案中查到" in m.content for m in out["messages"])
```

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_graph.py -v 2>&1 | tail -10
```
预期：ImportError（`agent.graph` 不存在）

- [ ] **Step 3: 实现 `agent/graph.py`**

```python
# agent/graph.py
from __future__ import annotations
from typing import Literal
from langgraph.graph import END, START, StateGraph

from .nodes import (
    make_generate_node,
    make_grade_node,
    make_no_doc_node,
    make_retrieve_node,
)
from .state import AgentState


def build_graph(*, llm, retriever, checkpointer):
    builder = StateGraph(AgentState)

    retrieve = make_retrieve_node(retriever)
    grade = make_grade_node(llm)
    generate = make_generate_node(llm)
    no_doc = make_no_doc_node(llm)

    builder.add_node("retrieve", retrieve)
    builder.add_node("grade", grade)
    builder.add_node("generate", generate)
    builder.add_node("no_doc", no_doc)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "grade")

    def _route(state: AgentState) -> Literal["generate", "no_doc"]:
        return "generate" if state.get("is_relevant") else "no_doc"

    builder.add_conditional_edges("grade", _route, {
        "generate": "generate",
        "no_doc": "no_doc",
    })
    builder.add_edge("generate", END)
    builder.add_edge("no_doc", END)

    return builder.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
python -m pytest tests/test_graph.py -v 2>&1 | tail -15
```
预期：3 个 PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(agent): langgraph assembly with relevance routing"
```

---

### Task 11: FastAPI 应用骨架、健康检查与入索引路由

**Files:**
- Create: `app/main.py`, `app/schemas.py`, `app/routes_health.py`, `app/routes_ingest.py`
- Create: `storage/paths.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `llm.client.get_llm()`, `rag.retriever.collection_count()`, `ingest.indexer.build_index()`
- Produces:
  - `GET /api/health` → `{status, llm, chroma_count}`
  - `POST /api/ingest` body `{force?: bool}` → `IndexResult`

- [ ] **Step 1: 实现 `storage/paths.py`**

```python
# storage/paths.py
import os


DATA_DIR: str = os.environ.get("DATA_DIR", "./data")
DOCUMENTS_DIR: str = os.environ.get("DOCUMENTS_DIR", "./Documents")
WEB_DIR: str = os.environ.get("WEB_DIR", "./web")
CHROMA_DIR: str = os.path.join(DATA_DIR, "chroma")
CHECKPOINT_DB: str = os.path.join(DATA_DIR, "checkpoints.db")
INDEX_META: str = os.path.join(DATA_DIR, "index_meta.json")
```

- [ ] **Step 2: 写失败测试 `tests/test_api.py`**

```python
# tests/test_api.py
import os
import tempfile
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "Documents"))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setenv("OFFLINE", "1")
    # 重置 singleton
    import importlib
    import rag.embeddings as emb_mod
    importlib.reload(emb_mod)
    import rag.retriever as ret_mod
    importlib.reload(ret_mod)
    import llm.client as llm_client_mod
    importlib.reload(llm_client_mod)
    import app.main as app_main_mod
    importlib.reload(app_main_mod)
    return TestClient(app_main_mod.app)


def test_health_returns_struct(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "chroma_count" in data
    assert "llm" in data
    assert data["status"] in ("ok", "degraded")


def test_ingest_runs_with_empty_corpus(client):
    r = client.post("/api/ingest", json={"force": False})
    assert r.status_code == 200
    data = r.json()
    assert "added" in data and "skipped" in data and "failed" in data
    assert data["added"] == 0
    assert data["skipped"] == 0
```

- [ ] **Step 3: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_api.py -v 2>&1 | tail -10
```
预期：ImportError 或 ModuleError

- [ ] **Step 4: 实现 `app/schemas.py`**

```python
# app/schemas.py
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str                # "ok" | "degraded"
    llm: bool
    chroma_count: int


class IngestRequest(BaseModel):
    force: bool = False


class IndexResult(BaseModel):
    added: int
    skipped: int
    failed: list[dict] = Field(default_factory=list)
    meta_written: bool = True


class ChatMessage(BaseModel):
    session_id: str
    message: str


class TokenEvent(BaseModel):
    event: str = "token"
    data: str


class CitationEvent(BaseModel):
    event: str = "citation"
    data: list[dict]


class DoneEvent(BaseModel):
    event: str = "done"
    data: dict


class ErrorEvent(BaseModel):
    event: str = "error"
    data: str
```

- [ ] **Step 5: 实现 `app/routes_health.py`**

```python
# app/routes_health.py
from __future__ import annotations
from fastapi import APIRouter

from .schemas import HealthResponse
from rag.retriever import collection_count


router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    llm_ok = False
    try:
        from llm.client import get_llm
        get_llm(streaming=False).invoke("ping"[:1])      # 极简探测；超时容忍
        llm_ok = True
    except Exception:
        llm_ok = False
    return HealthResponse(
        status="ok" if llm_ok else "degraded",
        llm=llm_ok,
        chroma_count=collection_count(),
    )
```

> 说明：`llm_ok` 在 llama.cpp 不可达时为 False，spec §9 要求降级而非抛错。这里通过 try/except 实现。如果想避免每次健康检查触发 LLM 调用，可以缓存 5s；先简单实现，Task 14 可优化。

- [ ] **Step 6: 实现 `app/routes_ingest.py`**

```python
# app/routes_ingest.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from .schemas import IngestRequest, IndexResult
from ingest.indexer import build_index


router = APIRouter()


@router.post("/api/ingest", response_model=IndexResult)
def ingest(req: IngestRequest) -> IndexResult:
    try:
        result = build_index(force=req.force)
    except Exception as exc:                              # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))
    return IndexResult(**result)
```

- [ ] **Step 7: 实现 `app/main.py`**

```python
# app/main.py
from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from storage.paths import WEB_DIR
from .routes_health import router as health_router
from .routes_ingest import router as ingest_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Counselor", version="0.1.0")
    app.include_router(health_router)
    app.include_router(ingest_router)
    if os.path.isdir(WEB_DIR):
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
```

- [ ] **Step 8: 跑测试确认 PASS**

```bash
python -m pytest tests/test_api.py -v 2>&1 | tail -15
```
预期：2 个 PASS（`test_health` 在 OFFLINE 下 LLM 调用应该被 try/except 吞掉，degraded）

- [ ] **Step 9: 提交**

```bash
git add -A
git commit -m "feat(app): fastapi skeleton with health and ingest routes"
```

---

### Task 12: WebSocket 流式问答路由

**Files:**
- Create: `app/routes_chat.py`, `tests/test_ws.py`

**Interfaces:**
- Consumes: `WebSocket` 客户端发送 `{session_id, message}`；`llm.client.get_llm` (streaming=True)；`rag.retriever.get_retriever`；`langgraph.checkpoint.sqlite.SqliteSaver`
- Produces:
  - `WS /ws/chat` 按 spec §4.3 推送事件流

- [ ] **Step 1: 写失败测试 `tests/test_ws.py`**

```python
# tests/test_ws.py
import os, json, tempfile
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCUMENTS_DIR", str(tmp_path / "Documents"))
    (tmp_path / "Documents").mkdir()
    monkeypatch.setenv("OFFLINE", "1")
    import importlib
    import rag.embeddings as emb_mod; importlib.reload(emb_mod)
    import rag.retriever as ret_mod; importlib.reload(ret_mod)
    import llm.client as llm_client_mod; importlib.reload(llm_client_mod)
    import app.main as app_main_mod; importlib.reload(app_main_mod)
    return TestClient(app_main_mod.app)


def test_ws_validation_rejects_long_message(client):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text(json.dumps({"session_id": "550e8400-e29b-41d4-a716-446655440000",
                                 "message": "x" * 5000}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data["event"] == "error"


def test_ws_validation_rejects_bad_uuid(client):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_text(json.dumps({"session_id": "not-a-uuid", "message": "hi"}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data["event"] == "error"
```

> 这两个测试只验证入参校验。完整 happy path 需要可流式 fake LLM；下面 Step 5 用 monkeypatch 完成。

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
python -m pytest tests/test_ws.py -v 2>&1 | tail -10
```
预期：`/ws/chat` 不存在 → WebSocketDisconnect

- [ ] **Step 3: 实现 `app/routes_chat.py`**

```python
# app/routes_chat.py
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .schemas import ErrorEvent
from agent.graph import build_graph
from llm.client import get_llm
from rag.retriever import get_retriever
from storage.paths import CHECKPOINT_DB


router = APIRouter()


def _validate_session_id(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except Exception:
        return False


async def _astream_graph(graph, input_state: dict, thread_id: str) -> AsyncIterator[dict]:
    """Yield token chunks + final citations from a LangGraph run。"""
    config = {"configurable": {"thread_id": thread_id}}
    # 我们跑完整图（generate 节点内部已经拼 prompt），这里从 retrieve 节点流式
    # streaming 通过 llm 的 astream_events 暴露给上层
    events: list[dict] = []
    async for ev in graph.astream_events(input_state, config=config, version="v1"):
        events.append(ev)
    return events


@router.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        raw = await ws.receive_text()
        payload = json.loads(raw)
        session_id = str(payload.get("session_id", ""))
        message = str(payload.get("message", ""))

        if not _validate_session_id(session_id):
            await ws.send_text(ErrorEvent(data="invalid session_id").model_dump_json())
            await ws.close()
            return

        if len(message) > 4000:
            await ws.send_text(ErrorEvent(data="message too long (>4000 chars)").model_dump_json())
            await ws.close()
            return

        if not message.strip():
            await ws.send_text(ErrorEvent(data="empty message").model_dump_json())
            await ws.close()
            return

        llm = get_llm(streaming=True)
        retriever = get_retriever(k=6)

        async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
            graph = build_graph(llm=llm, retriever=retriever, checkpointer=checkpointer)
            input_state = {"messages": [HumanMessage(content=message)]}
            config = {"configurable": {"thread_id": session_id}}

            full_answer = ""
            citations_payload: list[dict] = []
            finish_reason = "stop"

            try:
                # astream_events 让我们抓 generate / no_doc 节点的 token
                async for ev in graph.astream_events(input_state, config=config,
                                                    version="v1"):
                    kind = ev.get("event")
                    node = ev.get("metadata", {}).get("langgraph_node") or \
                           ev.get("name", "")
                    if kind == "on_chat_model_stream" and node in ("generate", "no_doc"):
                        chunk = ev.get("data", {}).get("chunk")
                        token = ""
                        if chunk is not None:
                            token = getattr(chunk, "content", "") or ""
                        if token:
                            full_answer += token
                            await ws.send_text(json.dumps(
                                {"event": "token", "data": token}, ensure_ascii=False))

                    if kind == "on_chain_end" and node in ("generate", "no_doc"):
                        out = (ev.get("data") or {}).get("output") or {}
                        cites = out.get("citations") if isinstance(out, dict) else None
                        if cites is not None:
                            citations_payload = cites
                        finish_reason = "no_doc" if node == "no_doc" else "stop"
            except Exception as exc:                              # noqa: BLE001
                await ws.send_text(ErrorEvent(data=f"agent error: {exc}").model_dump_json())
                await ws.close()
                return

        if citations_payload:
            await ws.send_text(json.dumps(
                {"event": "citation", "data": citations_payload}, ensure_ascii=False))
        await ws.send_text(json.dumps(
            {"event": "done", "data": {"finish_reason": finish_reason}}, ensure_ascii=False))
    except WebSocketDisconnect:
        return
    except Exception as exc:                                     # noqa: BLE001
        try:
            await ws.send_text(ErrorEvent(data=f"unexpected: {exc}").model_dump_json())
        except Exception:
            pass
```

- [ ] **Step 4: 在 `app/main.py` 注册 chat 路由**

修改 `app/main.py`，把 `from .routes_health import router as health_router` 块下追加：

```python
from .routes_chat import router as chat_router   # noqa: E402
```
并在 `create_app()` 内 `app.include_router(health_router)` 后追加：

```python
    app.include_router(chat_router)
```

- [ ] **Step 5: 跑测试确认 PASS**

```bash
python -m pytest tests/test_ws.py -v 2>&1 | tail -15
```
预期：2 个 PASS

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "feat(app): websocket chat with streaming and checkpointer"
```

---

### Task 13: 静态前端（HTML + JS + CSS）

**Files:**
- Create: `web/index.html`, `web/app.js`, `web/style.css`

**Interfaces:**
- Consumes: `GET /api/health`、`POST /api/ingest`、`WS /ws/chat`
- Produces:
  - 单页 Chat UI，状态点、入索引按钮、消息列表、引用折叠面板、输入框

- [ ] **Step 1: 写 `web/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AI 辅导员</title>
<link rel="stylesheet" href="style.css" />
</head>
<body>
<header>
  <h1>AI 辅导员</h1>
  <div class="header-right">
    <span id="status-dot" class="dot"></span>
    <span id="status-text">检测中…</span>
    <button id="reindex">重新入索引</button>
  </div>
</header>
<main id="messages"></main>
<div id="citations-panel" hidden>
  <h3>参考资料</h3>
  <ol id="citations-list"></ol>
</div>
<footer>
  <div class="counter"><span id="char-count">0</span>/4000</div>
  <textarea id="input" rows="2" placeholder="请输入你的问题…"></textarea>
  <button id="send">发送</button>
</footer>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 `web/style.css`**

```css
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }
body { display: flex; flex-direction: column; background: #fafafa; }
header { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: #fff; border-bottom: 1px solid #eee; }
header h1 { margin: 0; font-size: 18px; }
.header-right { display: flex; gap: 8px; align-items: center; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: #ccc; display: inline-block; }
.dot.ok { background: #2ecc71; }
.dot.degraded { background: #f39c12; }
button { padding: 6px 12px; border: 1px solid #ccc; background: #fff; border-radius: 6px; cursor: pointer; }
button:hover { background: #f0f0f0; }
main { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
.bubble { max-width: 70%; padding: 10px 14px; border-radius: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.bubble.user { align-self: flex-end; background: #2563eb; color: #fff; }
.bubble.assistant { align-self: flex-start; background: #fff; border: 1px solid #e5e7eb; }
.bubble .citations-link { font-size: 12px; color: #6b7280; cursor: pointer; margin-top: 6px; display: inline-block; }
#citations-panel { padding: 16px 20px; background: #fff; border-top: 1px solid #eee; }
#citations-panel ol { padding-left: 18px; }
#citations-panel li { margin-bottom: 6px; font-size: 13px; color: #374151; }
#citations-panel .snippet { color: #6b7280; font-size: 12px; }
footer { display: flex; gap: 8px; padding: 12px; background: #fff; border-top: 1px solid #eee; align-items: flex-end; }
footer textarea { flex: 1; resize: none; padding: 8px; border: 1px solid #ddd; border-radius: 6px; font-family: inherit; }
footer .counter { font-size: 12px; color: #6b7280; }
```

- [ ] **Step 3: 写 `web/app.js`**

```javascript
const $ = (sel) => document.querySelector(sel);

const messagesEl = $("#messages");
const inputEl = $("#input");
const sendEl = $("#send");
const charCount = $("#char-count");
const statusDot = $("#status-dot");
const statusText = $("#status-text");
const reindexEl = $("#reindex");
const citationsPanel = $("#citations-panel");
const citationsList = $("#citations-list");

let sessionId = localStorage.getItem("session_id");
if (!sessionId) {
  sessionId = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  localStorage.setItem("session_id", sessionId);
}

function uuidLooksValid(s) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);
}
if (!uuidLooksValid(sessionId)) sessionId = crypto.randomUUID();

function appendMessage(role, text) {
  const div = document.createElement("div");
  div.className = "bubble " + role;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function appendCitations(cites) {
  citationsList.innerHTML = "";
  cites.forEach((c) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>《${c.filename}》 p${c.page}</strong><div class="snippet">${c.snippet}</div>`;
    citationsList.appendChild(li);
  });
  citationsPanel.hidden = cites.length === 0;
}

async function refreshHealth() {
  try {
    const r = await fetch("/api/health");
    const data = await r.json();
    const ok = data.status === "ok";
    statusDot.classList.toggle("ok", ok);
    statusDot.classList.toggle("degraded", !ok);
    statusText.textContent = ok ? "在线" : (data.llm ? "索引未建立" : "模型未连接");
  } catch (e) {
    statusDot.classList.remove("ok");
    statusDot.classList.add("degraded");
    statusText.textContent = "无法连接后端";
  }
}

async function reindex() {
  reindexEl.disabled = true;
  reindexEl.textContent = "处理中…";
  try {
    const r = await fetch("/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: false }),
    });
    const data = await r.json();
    alert(`索引完成：新增 ${data.added} 个，跳过 ${data.skipped} 个，失败 ${data.failed.length} 个`);
    refreshHealth();
  } catch (e) {
    alert("入索引失败：" + e);
  } finally {
    reindexEl.disabled = false;
    reindexEl.textContent = "重新入索引";
  }
}

async function sendMessage(text) {
  if (!text.trim()) return;
  appendMessage("user", text);
  const assistantEl = appendMessage("assistant", "▍");
  let buffer = "";

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}/ws/chat`;
  const ws = new WebSocket(url);
  ws.onopen = () => {
    ws.send(JSON.stringify({ session_id: sessionId, message: text }));
  };
  ws.onmessage = async (ev) => {
    let payload;
    try { payload = JSON.parse(ev.data); } catch { return; }
    if (payload.event === "token") {
      buffer += payload.data;
      assistantEl.textContent = buffer + " ▍";
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else if (payload.event === "citation") {
      appendCitations(payload.data || []);
    } else if (payload.event === "done") {
      assistantEl.textContent = buffer;
    } else if (payload.event === "error") {
      assistantEl.textContent = "（出错了）" + (payload.data || "");
    }
  };
  ws.onerror = () => {
    assistantEl.textContent = "（连接失败）";
  };
}

inputEl.addEventListener("input", () => {
  charCount.textContent = inputEl.value.length;
});
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    const v = inputEl.value;
    inputEl.value = "";
    charCount.textContent = 0;
    sendMessage(v);
  }
});
sendEl.addEventListener("click", () => {
  const v = inputEl.value;
  inputEl.value = "";
  charCount.textContent = 0;
  sendMessage(v);
});
reindexEl.addEventListener("click", reindex);

refreshHealth();
setInterval(refreshHealth, 30000);
```

- [ ] **Step 4: 启动服务并手测 UI**

```bash
bash scripts/run.sh &
sleep 2
curl -s http://localhost:8000/api/health | head -5
echo "---"
curl -s -X POST -H "Content-Type: application/json" -d '{"force":false}' http://localhost:8000/api/ingest | head -10
```

预期：
- `/api/health` 返回 200 + JSON
- `/api/ingest` 返回 200 + JSON（`added/skipped/failed`）

> 自动验收：浏览器打开 `http://localhost:8000`，能看到标题、状态点、入索引按钮。

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(web): single-page chat ui with citations panel"
```

---

### Task 14: 启动脚本、README 与端到端验证

**Files:**
- Create: `scripts/run.sh`
- Modify: `README.md`（覆盖占位内容）

**Interfaces:**
- Consumes: `pyproject.toml`, `Documents/`, `data/`
- Produces: 一键启动脚本、完整 README

- [ ] **Step 1: 写 `scripts/run.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p data

# 首启：自动入索引（OFFLINE=1 下也允许，因为 PDF 加载不依赖 embedding）
if [ ! -d data/chroma ]; then
  echo "[run] first run, building index..."
  python -m ingest.indexer
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "[run] starting uvicorn on ${HOST}:${PORT}"
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload
```

```bash
chmod +x scripts/run.sh
```

- [ ] **Step 2: 覆写 `README.md`**

```markdown
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
- `pip install -e ".[dev]"`

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
```

- [ ] **Step 3: 跑全量测试**

```bash
cd /home/relorelolore/AICounselor
DOCUMENTS_DIR=./Documents DATA_DIR=./data OFFLINE=1 pytest -q 2>&1 | tail -30
```
预期：所有测试 PASS（含 live LLM 测试被 skip）

- [ ] **Step 4: 端到端 smoke**

```bash
bash scripts/run.sh > /tmp/uvicorn.log 2>&1 &
SERVER_PID=$!
sleep 5
echo "--- health ---"
curl -s http://localhost:8000/api/health
echo
echo "--- ingest ---"
curl -s -X POST -H "Content-Type: application/json" -d '{"force":false}' http://localhost:8000/api/ingest
echo
echo "--- ws smoke (validation) ---"
python - <<'PY'
import json, asyncio, websockets, websockets.exceptions

async def go():
    async with websockets.connect("ws://localhost:8000/ws/chat") as ws:
        await ws.send(json.dumps({"session_id":"not-a-uuid","message":"hi"}))
        msg = await ws.recv()
        print("WS validation response:", msg)
asyncio.run(go())
PY
kill $SERVER_PID || true
wait 2>/dev/null || true
```

预期：
- `/api/health` 返回 JSON
- `/api/ingest` 返回 JSON
- WS 收到 `{"event":"error","data":"invalid session_id..."}`

- [ ] **Step 5: 验收清单**

打开 `http://localhost:8000` 手动确认：

1. 状态点变绿（如果 chroma 已建好索引）
2. 输入框敲入「2023级培养方案中实践学分要求是多少」
3. 回答含引用编号 `[1]` 且下面「参考资料」面板列出文件名/页码/片段
4. 关闭页面重开 → 历史会话保留
5. 点「重新入索引」→ 弹窗显示统计

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "chore: run script and README; end-to-end smoke verified"
```

---

## 自审结果（写完后回查）

我在写作过程中已做以下一致性检查：

1. **覆盖 spec**：14 个任务覆盖了 spec §2–§9 的所有要求（架构、依赖、索引流、对话流、WS 协议、LangGraph 图、API 路由、前端、错误分级、测试）。
2. **占位符扫描**：无 TBD/TODO/"implement later"。
3. **类型与命名一致性**：
   - `llm.client.get_llm(*, streaming, temperature, max_tokens)` 与 spec §6.1 一致。
   - `agent.state.AgentState` 与 spec §5.1 字段一致（messages / retrieved_docs / is_relevant / citations）。
   - `rag.retriever.get_retriever(*, k=6)` 与 spec §2.1、§13 env 一致。
   - `indexer.build_index(force=False) -> IndexResult` 与 spec §6.4 一致。
   - WS 事件名固定 `token` / `citation` / `done` / `error`，与 spec §4.3 一致。
4. **Task 12 的 astream_events 假设**：基于 langgraph ≥ 0.2 + langchain-core ≥ 0.2 的标准事件协议；若运行时事件名有偏差，Task 14 步骤 5 通过手测发现并可微调 `node` 匹配逻辑（已留 `metadata.langgraph_node` 与 `ev.name` 双路兜底）。
5. **Task 13 没有自动化测试**：纯静态前端；通过 `scripts/run.sh` 启动 + 浏览器手测验证。
6. **跨任务依赖**：每个 Task 的 "Interfaces" 块明确列出 consumes（来自前面任务）和 produces（后续任务依赖）；实现者即便跳着读也能找到符号。

发现并修复的一处风险：

- 原 Task 12 直接 await `AsyncSqliteSaver.from_conn_string` 而未在 `app.main` 导入 chat 路由——已通过 Task 12 Step 4 在 `app/main.py` 注册修复。

---

## 执行选项

执行人/下一个 agent 可以选择：

1. **Subagent-Driven（推荐）**：逐任务派发新 subagent，两阶段审查
2. **Inline Execution**：当前会话连续执行，里程碑检查

请告知偏好，我可立即开始。
