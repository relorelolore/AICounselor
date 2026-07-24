# AI 辅导员 Agent 设计规范

- 日期：2026-07-24
- 状态：已批准，等待实现
- 范围：单次实现计划可覆盖

## 1. 概述

构建一个本地运行的 AI 学业/课程辅导员智能体。学生在 WebUI 中提问，Agent 从 `Documents/` 中的资料检索相关片段，由 llama.cpp 本地模型生成回答，并显示引用来源。会话可持久化。

### 1.1 核心需求

- **角色**：学业/课程咨询师，基于校内文档回答学生关于培养方案、课程选修、培养要求等问题
- **RAG 源**：`Documents/*.pdf` / `*.pptx` / `*.docx`
- **WebUI**：FastAPI + 原生 HTML+JS（单页 Chat 风格）
- **LLM**：llama.cpp 本地服务 `http://localhost:8848/v1`（`g0chu-Qwen3.6-35B-A3B-NVFP4`，context 102400，embedding 2048）
- **Embedding**：本地 `sentence-transformers`（`BAAI/bge-m3`，多语种、中文友好）
- **能力**：RAG + 持久会话记忆 + 多轮上下文
- **框架**：LangChain + LangGraph

### 1.2 不做

- 多 Agent 路由、Web 搜索工具、其它角色
- 远程托管、鉴权、用户体系（单进程本地服务）
- Word/PPT 的高保真排版还原（仅取文本）

## 2. 架构

### 2.1 进程拓扑

```
浏览器 (单页 HTML+JS, web/)
   │   WebSocket /ws/chat (流式)
   │   HTTP GET  /api/sessions, /api/health
   │   HTTP POST /api/ingest        # 触发重新入索引
   ▼
FastAPI (app/main.py)
   │
   ├──► Agent  (agent/graph.py)        ─ LangGraph 实例
   │       │
   │       ├──► Retriever (rag/retriever.py) ─ Chroma 查询
   │       └──► LLM  (llm/client.py) ─ OpenAI 兼容 → http://localhost:8848/v1
   │
   ├──► Ingester (ingest/indexer.py)   ─ 扫描 Documents/ 切分嵌入入库
   │
   └──► Storage (storage/)
           ├── chroma/  (向量库持久化)
           ├── checkpoints.db  (LangGraph SqliteSaver)
           └── index_meta.json (源文件指纹)
```

### 2.2 目录布局

```
AICounselor/
├── app/                  # FastAPI 入口、路由
│   ├── main.py
│   ├── routes_chat.py
│   ├── routes_ingest.py
│   └── schemas.py
├── agent/                # LangGraph 图与状态
│   ├── graph.py
│   ├── state.py
│   └── nodes.py
├── rag/                  # 检索器、文本切分、citation
│   ├── retriever.py
│   ├── splitter.py
│   └── citations.py
├── ingest/               # 文档入索引
│   ├── indexer.py
│   ├── loaders.py
│   └── fingerprint.py
├── llm/                  # llama.cpp 客户端
│   └── client.py
├── storage/              # 路径常量
│   └── paths.py
├── web/                  # 静态前端
│   ├── index.html
│   ├── app.js
│   └── style.css
├── Documents/            # RAG 文档源（用户提供）
├── data/                 # 生成：chroma/、checkpoints.db、index_meta.json
├── scripts/
│   └── run.sh
├── tests/
│   ├── test_ingest.py
│   ├── test_retriever.py
│   ├── test_graph.py
│   ├── test_api.py
│   └── test_llm.py
├── docs/superpowers/specs/
├── pyproject.toml
└── README.md
```

### 2.3 职责边界

- `agent/` 只懂「检索 → 回答」，不直接操作文件
- `ingest/` 提供 CLI（`python -m ingest.indexer`）触发入索引；前端通过 `/api/ingest` POST 调用同一函数，避免双入口竞争
- 会话通过 `thread_id` 透传到 LangGraph，由 `SqliteSaver` 持久化

## 3. 依赖

`pyproject.toml`：

```toml
[project]
name = "ai-counselor"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "langchain>=0.2",
    "langchain-community>=0.2",
    "langgraph>=0.2",
    "langgraph-checkpoint-sqlite>=0.1",
    "langchain-chroma>=0.1",
    "langchain-huggingface>=0.1",
    "sentence-transformers>=3.0",
    "chromadb>=0.5",
    "openai>=1.40",                # 与 llama.cpp 兼容的客户端
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pypdf>=5.0",
    "python-pptx>=1.0",
    "docx2txt>=0.8",
    "unstructured>=0.14",         # PPT/DOCX 加载兜底
    "pydantic>=2.6",
    "websockets>=12",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27"]
```

## 4. 数据流

### 4.1 索引流程（启动时自动 / 手动触发）

```
Documents/*.pdf|*.pptx|*.docx
   │
   ├── 1. fingerprint.hash_file(path) → 对比 index_meta.json，跳过未变更文件
   │
   ├── 2. loaders.load(path) 根据后缀选 PyPDFLoader / UnstructuredPowerPointLoader / UnstructuredWordDocumentLoader
   │       → 原始 Document 列表（每页/每段一条）
   │
   ├── 3. splitter.split(docs, chunk_size=500, chunk_overlap=80,
   │                       separators=["\n\n", "\n", "。", ".", " ", ""],
   │                       keep_separator=True)
                  （RecursiveCharacterTextSplitter 会从最长分隔符开始尝试，
                   直到单段 <= chunk_size；超过则继续按次级分隔符再切）
   │
   ├── 4. embeddings.embed_documents(chunks) (BAAI/bge-m3, normalize=True)
   │
   ├── 5. chroma.add_documents(chunks, ids=[{file_hash}-{i}, ...])
   │
   └── 6. 更新 index_meta.json：{file_path: {hash, mtime, chunks_count, status}}
```

### 4.2 单轮对话流程

```
浏览器 WS.send({session_id, message})
   │
FastAPI route → graph.astream_events(...)
   │
   ▼
LangGraph（图见 §5）
   │
   ▼
WebSocket push "token" 增量 / "citation" 引用 / "done" 结束
```

### 4.3 WebSocket 协议

| 方向 | 事件 | 数据 |
|---|---|---|
| 客户端 → 服务端 | — | `{"session_id": str, "message": str}` |
| 服务端 → 客户端 | `token` | `{"event":"token","data":"..."}` (增量片段) |
| 服务端 → 客户端 | `citation` | `{"event":"citation","data":[{"filename":str,"page":int,"snippet":str}]}` |
| 服务端 → 客户端 | `done` | `{"event":"done","data":{"finish_reason":"stop"|"no_doc"}}` |
| 服务端 → 客户端 | `error` | `{"event":"error","data":str}` |

`session_id` 由前端生成 UUID 持久存在 localStorage，重连时复用。

## 5. LangGraph 图

### 5.1 状态

```python
# agent/state.py
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

### 5.2 节点

| 节点 | 输入 | 行为 | 输出 |
|---|---|---|---|
| `retrieve` | `messages[-1].content` | `retriever.invoke(query)` 取 top-k=6 | `retrieved_docs` |
| `grade` | `retrieved_docs` + query | LLM 判断「是否能基于此回答」二分类（YES/NO）；解析失败默认 False | `is_relevant` |
| `generate` | messages + retrieved_docs | 拼 prompt → LLM 流式；收集元数据 | 更新 `messages`，产出 `citations` |
| `no_doc` | messages | 直接 LLM，但不强制基于资料 | 更新 `messages` |

### 5.3 边

```
START → retrieve → grade
                      ├── True  → generate → END
                      └── False → no_doc   → END
```

条件边函数 `route_after_grade(state) -> Literal["generate","no_doc"]`。

### 5.4 系统提示词与节点 prompt

**系统提示词（generate 节点）**

```
你是学校学业辅导员。请仅基于【参考资料】回答学生关于培养方案、课程、毕业要求等问题。
如果参考资料不能回答，请礼貌告知「未在培养方案中查到相关说法，建议咨询学院教务」。
回答结尾用 [1] [2] ... 标注引用，对应参考资料中的段落。
回答使用与学生提问相同的语言。
```

**`generate` 节点 prompt 模板**

```
参考资料：
{docs_as_cited_list}

历史对话：
{history}

学生问题：{question}

请用中文生成回答（含引用编号）。引用编号必须出现在句末。
```

`docs_as_cited_list` 的构造规则：

```
[1] 来源：《文件名》 第 N 页
    内容：{doc.page_content[:300]}

[2] 来源：《文件名》 第 M 页
    内容：{doc.page_content[:300]}
...
```

**`grade` 节点 prompt 与解析**

```
参考资料：
{docs_as_cited_list_compact}

学生问题：{question}

请判断参考资料是否包含回答该问题所需的关键信息。
仅输出 JSON，不要其它文字：{"relevant": true|false, "reason": "..."}
```

`docs_as_cited_list_compact` 仅含 `filename + page + page_content[:150]` 三列，长度可控。节点解析该 JSON：`relevant=true` → 路由 `generate`，否则 `no_doc`。JSON 解析失败一律视为 False。

## 6. 关键模块说明

### 6.1 `llm/client.py`

```python
from langchain_openai import ChatOpenAI
from .config import LLAMACPP_BASE_URL, MODEL_NAME

def get_llm(streaming: bool = True, temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=LLAMACPP_BASE_URL,          # "http://localhost:8848/v1"
        api_key="not-needed",
        model=MODEL_NAME,                    # "g0chu-Qwen3.6-35B-A3B-NVFP4"
        streaming=streaming,
        temperature=temperature,
        max_tokens=2048,
    )
```

### 6.2 `rag/retriever.py`

```python
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

DB_DIR = "data/chroma"
COLL = "counselor"

_emb = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

db = Chroma(persist_directory=DB_DIR, embedding_function=_emb, collection_name=COLL)
retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 6})
```

### 6.3 `rag/citations.py`

构造 `{filename, page, snippet}` 元数据列表，前端在回答下方展示。

### 6.4 `ingest/indexer.py`

CLI 入口：`python -m ingest.indexer`。提供 `build_index(force: bool = False) -> IndexResult` 给 `/api/ingest` 调用。`IndexResult` 字段：`{added, skipped, failed: [{path, error}]}`。

## 7. API 路由

| 方法 | 路径 | 行为 | 入参 | 返回 |
|---|---|---|---|---|
| GET | `/api/health` | 健康检查 | — | `{status:"ok", llm:bool, chroma_count:int}` |
| POST | `/api/ingest` | 重新入索引（force=true 时重建全部） | `{force?: bool}` | `IndexResult` |
| WS  | `/ws/chat` | 流式问答 | `{session_id, message}` | 见 §4.3 |
| GET | `/` | 静态前端 | — | `web/index.html` |

## 8. 前端（`web/`）

单页 Chat 风格：
- 顶部：「AI 辅导员」标题 + 「重新入索引」按钮 + 状态点（绿/黄/红）
- 中部：滚动消息列表
  - 用户消息：右对齐气泡
  - 助手消息：左对齐气泡，下方「引用」折叠面板，列出 `filename + page + snippet`
- 底部：多行输入框 + 发送；消息长度实时计数
- 启动时 GET `/api/health`：状态点反映模型与索引可用
- 点击「重新入索引」→ POST `/api/ingest` → 提示「N added / M skipped / K failed」

不使用任何前端框架；原生 `fetch` + `WebSocket`。

## 9. 错误处理

| 场景 | 行为 |
|---|---|
| llama.cpp 不可达 | `/api/health` 标红；`/ws/chat` 推送 `{"event":"error","data":"模型服务异常"}`；前端显示气泡 |
| Chroma 索引空（未触发入索引） | `retrieve` 返回 `[]` → `grade` False → `no_doc` 节点 |
| 检索到但 grader 全 False | `no_doc`：「未在《xxx》中查到相关说法，建议咨询学院教务」 |
| 文档解析失败 | `loaders.load` 抛错被 `indexer` 捕获，记入 `index_meta.json.failed:[...]`，UI 显示「K 个文件失败」 |
| Embedding 模型未下载 | 首启下载阻塞；提供 `OFFLINE=1` 跳过（需本地缓存命中） |
| 扫描件 PDF（无文本层） | loader 返回空 page → splitter 拿不到文本 → 元数据 `failed` |
| 消息 > 4000 chars | WS 推送 `error` |
| `session_id` 非 UUID | HTTP 400 |

## 10. 测试

`pytest` + `pytest-asyncio`。

| 文件 | 覆盖 |
|---|---|
| `tests/test_ingest.py` | 给定 mock Documents/，跑入索引 → Chroma 命中查询 |
| `tests/test_retriever.py` | 简单查询返回 top-k 中文片段，断言 snippet 含 query 关键词 |
| `tests/test_graph.py` | 注入假 retriever（返回空/相关/不相关）+ 假 LLM，验证三条分支 |
| `tests/test_api.py` | `TestClient` 验证 `/api/health`、`/api/ingest`、WebSocket 协议 |
| `tests/test_llm.py` | 实际打 `http://localhost:8848/v1/models` 与最小 chat（服务未起则 skip） |

CI 不强制要求 llm 服务跑通；`test_llm.py` 默认 skip if `LLAMACPP_BASE_URL` 不可达。

## 11. 启动脚本（`scripts/run.sh`）

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ ! -d data/chroma ] && python -m ingest.indexer || echo "[skip] index exists"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后浏览器打开 `http://localhost:8000`。

## 12. 验收清单

1. `bash scripts/run.sh` 启动；首次自动入索引，控制台打印加载文件与 chunk 数
2. 前端首页状态点绿，`/api/health` 返回 `chroma_count > 0`
3. 提问「2023级培养方案中实践学分要求是什么？」返回带 `[1] [2]` 引用、可点击展开 snippet
4. 提问与文档无关 → 「未找到相关政策，建议咨询学院教务」
5. 关闭页面再打开 → 历史会话保留（同一 `session_id` 继续）
6. `pytest -q` 全部通过（llm 相关测试在 llama.cpp 未起时 skip）

## 13. 配置（环境变量）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLAMACPP_BASE_URL` | `http://localhost:8848/v1` | llama.cpp OpenAI 兼容接口 |
| `MODEL_NAME` | `g0chu-Qwen3.6-35B-A3B-NVFP4` | 模型 id |
| `EMBED_MODEL` | `BAAI/bge-m3` | sentence-transformers 模型 |
| `DOCUMENTS_DIR` | `./Documents` | RAG 源 |
| `DATA_DIR` | `./data` | Chroma、checkpoints、meta |
| `OFFLINE` | `0` | `1` 跳过 embedding 模型下载 |
| `CHUNK_SIZE` | `500` | 切分 |
| `CHUNK_OVERLAP` | `80` | 重叠 |
| `RETRIEVE_K` | `6` | top-k |

## 14. 后续（不在本次范围）

- Re-ranking 模型（bge-reranker）提升 top-k 精度
- 文档增量上传 UI（当前仅扫描 `Documents/`）
- 多角色切换（心理咨询/职业规划）走 LangGraph 子图
- 后端鉴权 + 用户体系
