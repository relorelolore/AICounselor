# AI 辅导员 Agent

本地 RAG 驱动的学业辅导员：基于 LangChain + LangGraph + Chroma + bge-m3 + llama.cpp。

## 功能

- 在 `Documents/` 下放入 PDF/PPT/Word 文档
- 自动入索引（首启或点「重新入索引」）
- 单页 WebUI 提问，模型基于本地 llama.cpp 生成
- 多会话 UI：左侧栏管理多个会话，所有状态本地持久化（`localStorage`），后端无状态

## 准备

- Python 3.11+
- 运行中的 llama.cpp server：`http://localhost:8848/v1`
- `uv sync --extra dev` (deps already installed from Task 1; this is just a sanity check)

## 启动

```bash
bash scripts/run.sh
```

打开浏览器访问 `http://localhost:8000`。

## Web UI

打开后默认进入 **多会话 ChatGPT 风格**界面，所有状态保存在浏览器 `localStorage`（key 为 `counselor:state`），**后端不持久化任何对话**——重启服务器、刷新页面都不会丢失会话。

### 左侧栏（多会话管理）

- **＋ 新会话**：创建新对话，自动生成 UUID 标题。
- **点击会话标题**：在右侧主区域切换并加载该会话的完整历史。
- **点击顶栏会话名 / ⋯ → 重命名**：原地编辑会话标题。
- **⋯ → 删除会话 / 清空全部会话**：单个或批量清理（不可撤销，会先弹确认）。
- **≡ 折叠按钮**：折叠侧边栏，最大化主区域（移动端默认收起）。

每个会话项显示**自动标题**（取首条用户消息的前 24 字 + `…`）和**相对时间**（刚刚 / N 分钟前 / 昨天 / M/D）。

### 主区域

- Markdown 渲染：标题、列表、`code`、围栏代码块、表格、加粗/斜体、行内链接。
- **引用 chips**：模型回答末尾出现的 `[文件名 p.N]` 小芯片，点击后从右侧滑出**参考资料抽屉**（drawer），里面是该条引用对应的文档片段、文件名、页码。
- 输入区字符计数（`0/4000`）、**发送** / **停止** 切换、Shift+Enter 换行 / Enter 发送。
- 流式响应中显示**打字指示器**，并在 WS 异常时弹出 toast 提示。
- **重建索引**按钮：手动触发 Chroma 全量重建（不进侧边栏）。

### 持久化

- 所有会话、消息、引用都在 `localStorage["counselor:state"]`。
- **会话 id**（UUID v4）只在 WebSocket 帧里作为审计字段携带，不参与任何服务端状态。
- 重启 `bash scripts/run.sh` 或 `pkill -9 -f uvicorn` 都不会丢失会话。
- 浏览器清缓存 / 隐私模式 → 会丢；想"重置"就在 ⋯ → 清空全部会话，或浏览器 DevTools 删除 `counselor:state`。

### 响应式

- 桌面：左栏 + 主区 + drawer 三栏，drawer 浮于主区右侧。
- 移动端（< 768px）：侧边栏默认收起，drawer 全屏覆盖，主区占满。

## 测试

```bash
pytest -q
```

`tests/test_llm.py::test_live_invoke` 默认 skip；启用：

```bash
SKIP_LIVE_LLM=0 pytest tests/test_llm.py -v
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
pkill -9 -f uvicorn
rm -rf data/
bash scripts/run.sh   # 自动重建索引 + chroma
```

> **关于 `data/checkpoints.db`**：旧版 SqliteSaver 留下的检查点文件在 `bash scripts/run.sh` 启动时会自动删除（`scripts/run.sh` 里的一次性迁移，幂等）。如果手动 `rm -rf data/`，该文件也会随 Chroma 索引一并清掉，无需单独处理。

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
