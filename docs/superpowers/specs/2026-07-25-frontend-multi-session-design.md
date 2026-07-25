# 多会话客户端前端与无状态后端设计

**日期**：2026-07-25
**作者**：Claude (brainstorming session)
**状态**：v0.1 approved
**增量基线**：2026-07-24 主设计（v1）+ v2 增补（ReAct）

---

## §0 目标

把 AI 辅导员前端从「单会话、引用挂全局面板」改造成「多会话、客户端持久化、ChatGPT 风格布局」；同时把后端从「带 SqliteSaver 检查点的会话」简化为「无状态函数式 ReAct runner」。一句话：服务端不存任何会话状态，所有历史由浏览器持有。

非目标：
- 用户系统、鉴权、远程托管（CLAUDE.md 已排除）
- 暗色模式（首版预留 CSS 媒体查询占位，不实现）
- markdown 完整语法（首版覆盖标题/列表/代码块/粗体/链接/行内 code）
- IndexedDB、Service Worker、PWA

---

## §1 架构与边界

```
┌───────────────────── 浏览器（localStorage）────────────────────┐
│                                                               │
│  web/app.js 单一模块，模块内按「职责」切子函数：                │
│  • store        — 加载/保存 localStorage 与 in-memory state  │
│  • wsClient     — 单条 WS 连接、事件分发                       │
│  • renderer     — 渲染会话列表、消息列表、引用                 │
│  • inputCtl     — 文本框、发送、停止按键                       │
│  • sidebarCtl   — 折叠/展开/新建/重命名/删除                   │
│  • chatActions  — 新建/切换/删除/重命名会话                     │
│                                                               │
│  内存中：state = { chats, activeId }                          │
│  落盘：每次 mutation 后 save()                                │
└───────────────────────┬───────────────────────────────────────┘
                        │ WS {session_id, history:[…]}
                        ▼
┌───────────────────── FastAPI 后端 ────────────────────────────┐
│  app/routes_chat.py                                           │
│    接收 history → 构造 messages                               │
│    build_graph(llm, retriever)  ← 不再传 checkpointer         │
│    graph.ainvoke({messages: history})                          │
│    流式发 token + citation + done                             │
│    citations 只从本轮（last HumanMessage 之后）取             │
└───────────────────────────────────────────────────────────────┘
```

关键边界：
- 客户端拥有「会话是什么、什么时候叫它」的全部知识；服务端只是个 stateless ReAct runner。
- 启动时若 localStorage 是空的 → 自动新建 1 个空会话并设为 active。
- 多 tab：不做实时同步（本地服务，单 tab 就够）；约定后写覆盖先写。
- `session_id` == `chat.id`，保证同一 chat 多次发送沿用同一 id（为将来审计 / 统计 / 限流留 hook）。

---

## §2 localStorage 数据模型

单一 key `counselor:state`：

```js
{
  version: 1,
  activeId: "uuid-...",
  chats: [
    {
      id: "uuid-...",
      title: "二次函数顶点公式",          // 首次发送后从首条消息截取
      createdAt: 1722432000000,           // Date.now()
      updatedAt: 1722432500000,
      messages: [
        { role: "user",      content: "...", ts: ... },
        { role: "assistant", content: "...", ts: ...,
          citations: [{filename, page, snippet}, ...] },
        { role: "tool",      content: "",    tool: "search_documents",
          status: "called" }               // 仅用于 UI 显示「正在检索」
      ]
    },
    ...
  ]
}
```

要点：
- `messages` 用 `role: "user"|"assistant"|"tool"`（与 LangChain `BaseMessage` 抽象对应）。
- `citations` 跟 assistant 消息共存（避免再像 v1 那样挂全局引用面板，引用永远跟着触发它的助手消息走）。
- `tool` 消息是 ephemeral UI state：实际发送给后端时不带 tool 消息，只发 user+assistant 文本，model 看到的就是干净历史。
- 启动时校验 `version`，未来 schema 升级写迁移函数。

标题生成（local heuristic，不调 LLM）：
```js
function autoTitle(text) {
  // 去掉前后空白，取前 MAX_TITLE_LEN 个字符；若全是标点 / 空白，回退 "新会话"
  const t = text.trim().replace(/\s+/g, " ");
  if (!t) return "新会话";
  return t.slice(0, 24) + (t.length > 24 ? "…" : "");
}
```
仅当 chat 当前 title 严格等于 "新会话" 时才覆盖；用户手动重命名过就不再覆盖。

---

## §3 WS 协议 & 后端改造

### §3.1 新协议

**Client → Server**（每条 WS 消息只有这一帧）：
```json
{
  "session_id": "uuid",
  "history": [
    { "role": "user",      "content": "..." },
    { "role": "assistant", "content": "..." },
    { "role": "user",      "content": "今天的问题" }
  ]
}
```

**Server → Client**（沿用现有 4 类事件，**仅过滤逻辑调整**）：
- `token` `{data: "..."}` — assistant 完整内容（保持现状，单事件非增量；spec v2.6 留作后续优化）
- `citation` `{data: [{filename, page, snippet}]}`
- `done` `{data: {finish_reason: "stop"}}`
- `error` `{data: "..."}`

### §3.2 后端关键改动（`app/routes_chat.py`）

| 改动点 | 旧 | 新 |
|---|---|---|
| 校验输入 | `message` 字段 | `history` 数组（最后一条必为 `user`，且不含 `tool` role — 前端在 §5.3 处已过滤） |
| 构造 messages | `[HumanMessage(content=message)]` | `BaseMessage` 列表：`user`→`HumanMessage`、`assistant`→`AIMessage`；遇到未知 role 报错 |
| graph 装配 | `build_graph(..., checkpointer=AsyncSqliteSaver(...))` | `build_graph(llm, retriever)` — **无 checkpointer** |
| config | `{"configurable": {"thread_id": session_id}}` | 删掉（`session_id` 字段仍接收并存档日志，但不参与图运行；为将来服务端审计 / 限流 / 统计留 hook） |
| citation 提取 | diff prior vs final messages（依赖 ID 集合） | 仅从最后一条 `HumanMessage` 之后的所有 `ToolMessage` 取 |

新引用过滤算法：
```python
def _extract_current_turn_citations(messages):
    last_human_idx = max(
        (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)),
        default=-1,
    )
    out = []
    seen = set()
    for m in messages[last_human_idx + 1:]:
        if isinstance(m, ToolMessage) and m.name == "search_documents":
            for c in to_citations(m.artifact or []):
                key = (c["filename"], c["page"])
                if key not in seen:
                    seen.add(key); out.append(c)
    return out
```
→ 前端每次发新问题时，本轮 `ToolMessage` 是唯一的新引用源；上一轮的引用不会泄漏到新一轮。

### §3.3 移除 SqliteSaver

- 删除 `storage/paths.py::CHECKPOINT_DB` 常量
- `data/checkpoints.db` 若存在则启动时自动删除一次（一次性迁移；写在 `scripts/run.sh` 启动前 hook 中）
- `app/routes_chat.py` 不再 import `AsyncSqliteSaver`
- `agent/graph.py::build_graph` 的 `checkpointer` 参数保留并默认 `None`，向后兼容现有 `test_graph.py`
- 文档：`CLAUDE.md` 已知陷阱表里把 SqliteSaver 相关行移除/更新

### §3.4 新增依赖

无新依赖（前端依赖现代浏览器近 2 年版本，已满足）。

---

## §4 UI 布局

### §4.1 桌面布局（≥ 768px）

```
┌─────────────────────────────────────────────────────────────┐
│ ┌─────────────┐ ┌────────────────────────────────────────┐  │
│ │ ≡ AI辅导员  │ │ ▾ 二次函数顶点公式       ●在线  ⋯      │  │ ← Top bar
│ │             │ ├────────────────────────────────────────┤  │
│ │ ＋ 新会话    │ │                                        │  │
│ │             │ │   ┌────────────────────────────┐       │  │
│ │ ▼ 今天       │ │   │ 用户消息 → 灰色气泡 右上   │       │  │
│ │   二次函数…  │ │   └────────────────────────────┘       │  │
│ │   概率…     │ │                                        │  │
│ │             │ │          ┌─────────────────────┐         │  │
│ │ ▼ 昨天       │ │          │ 助手气泡 ← 浅色  左 │         │  │
│ │   物理…     │ │          │ ┌─[引 1] [引 2]─┐  │         │  │
│ │             │ │          │ └──────────────┘  │         │  │
│ │ ─────────  │ │          │  解释文字         │         │  │
│ │             │ │          └─────────────────────┘         │  │
│ │             │ │                                        │  │
│ │             │ │   ▍ 助手正在输入…                       │  │
│ │             │ ├────────────────────────────────────────┤  │
│ │             │ │ ┌────────────────────────────────────┐ │  │
│ │             │ │ │ 输入框                                ↗│ │  │
│ │             │ │ └────────────────────────────────────┘ │  │
│ └─────────────┘ └────────────────────────────────────────┘  │
│   260px          flex 1                                    │
└─────────────────────────────────────────────────────────────┘
```

**配色（"现代简洁 + 主色调"）**
- 主色：`#2563eb`（蓝）
- 背景：`#ffffff`，聊天区：`#fafafa`
- 文字主：`#0f172a`，次：`#64748b`
- 边框：`#e5e7eb`，hover：`#f1f5f9`
- 助手气泡：`#f1f5f9` 圆角 16px；用户气泡：`#2563eb` 文字白
- 圆角统一 12–16px，按钮 hover 有 0.1s ease 微动效
- 字体：`Inter, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`

### §4.2 侧边栏（260px，可折叠至 56px）

| 元素 | 行为 |
|---|---|
| 顶部按钮 `≡` | 折叠/展开（按钮始终可见） |
| `＋ 新会话` | 创建一个空 chat，切到 active，清空聊天区 |
| 分组标题 `▼ 今天 / 昨天 / 本周 / 更早` | 不可点击，仅展示（按 updatedAt 分组） |
| 会话条目 | hover 时显示 `⋯` 菜单（重命名、删除）；点击切换 active |
| 当前 active 条目 | 背景 `#eff6ff` 左侧 3px 蓝色 border |
| 会话标题溢出 | 单行 ellipsis |

### §4.3 消息气泡

- **用户**：右对齐，`max-width: 70%`，蓝底白字，圆角 `16px 16px 4px 16px`
- **助手**：左对齐，`max-width: 80%`，浅灰底，圆角 `16px 16px 16px 4px`，markdown 渲染
  - 第一版：自写 ~80 行轻量 markdown 渲染器（支持 `**bold**` `# h1-h3`、列表、代码块 ```、行内 `code`、链接），不引入 marked.js 库
  - 引用：assistant 气泡下方一行 `chip`（`[引 1] [引 2]`），点击切换右侧抽屉显示该引用的 snippet
- **tool 状态指示**：助手回复过程中显示 `▍ 检索中…` 然后消失（不是真消息，是临时 UI 状态）

### §4.4 抽屉式引用面板

- 右侧从屏幕外滑入，width 320px，背景白，阴影
- 列 `[{filename, page, snippet}]`，snippet 多行省略
- ESC 或点击外部关闭
- 移动端：抽屉变成底部 sheet

### §4.5 移动布局（< 768px）

- 侧边栏默认折叠，只在点击顶部 `≡` 时全屏覆盖显示（带半透明遮罩）
- 聊天区占满
- 输入框贴底，键盘弹出时通过 `visualViewport` API 适配

---

## §5 前端模块拆分 & 数据流

### §5.1 文件结构

```
web/
├── index.html       ← 静态骨架：sidebar / topbar / chat / input
├── style.css        ← 全部样式（CSS variables 集中 token）
└── app.js           ← 单一模块；内部分区（按区加注释）
```

`app.js` 内部按职责分块（估 ~700 行）：

| 区 | 行数估 | 职责 |
|---|---|---|
| 常量与 utils | ~30 | `MAX_TITLE_LEN`, `uuidv4`, `escapeHtml`, `formatRelativeTime` |
| **store** | ~80 | `loadState() / saveState() / mutate(fn)` |
| **wsClient** | ~70 | 单例 `connect(history)` 收事件分发给回调 |
| **renderer** | ~200 | `renderSidebar()` `renderChat()` `renderMessage()` `renderCitations()` `renderEmptyState()` |
| **inputCtl** | ~60 | textarea 输入、Enter 发送、Shift+Enter 换行、char 计数 |
| **sidebarCtl** | ~60 | 折叠按钮、新建按钮、context menu |
| **chatActions** | ~100 | `createChat` `switchChat` `renameChat` `deleteChat` `sendInActiveChat` |
| **markdown** | ~80 | 自写轻量 md → html |
| **event glue** | ~80 | 把 UI 事件接到 store + renderer + wsClient |
| **boot** | ~30 | `init()` |

### §5.2 单向数据流

```
        ┌──────────────┐
  UI 事件 ──→ chatActions ──→ store.mutate() ──→ saveState() + re-render
        │                                ▲
        └─→ wsClient.send(history) ──────┘
                            │
                            ▼ 收到 token / citation / done
                          renderer.updateLive()  (局部更新，不重渲染整个列表)
```

要点：
- **mutation 都走 `store.mutate(fn)`**，里面 `fn(state)` 改 in-memory state，最后自动 `saveState()` + 触发 re-render。
- 渲染分两种：
  - **全量渲染**（store 变化、切换 chat）：`renderSidebar()` + `renderChat()`
  - **增量更新**（WS 收 token）：只改当前 assistant 气泡的 `textContent`，不重渲染整列表
- 渲染用 vanilla DOM API（不引入框架），每个渲染函数是 idempotent 的。
- 状态形状：`store.state = { version, activeId, chats: [...] }`。

### §5.3 关键流程

**启动**
```
boot()
  ├─ store.load()              // 读 localStorage
  ├─ 若空：mutate(s => { s.chats.push(blankChat()); s.activeId = chats[0].id })
  ├─ renderer.renderSidebar()
  ├─ renderer.renderChat()
  ├─ inputCtl.attach()
  ├─ sidebarCtl.attach()
  ├─ healthCheck() + 每 30s 刷新
  └─ 顶栏菜单 attach (重命名、删除、清空全部)
```

**发送消息**
```
inputCtl.onSubmit(text):
  ├─ 若 text 空白 → return
  ├─ chatActions.sendInActiveChat(text):
  │    ├─ mutate(s => { active.messages.push({role:'user', content:text, ts:Date.now()}) })
  │    ├─ 若 active.title === "新会话" → mutate 改成 autoTitle(text)
  │    ├─ renderer.renderChat()
  │    ├─ renderer.appendLiveAssistantBubble()
  │    └─ wsClient.connect(history):
  │         history = active.messages.filter(m => m.role !== 'tool')
  │                                .map(m => ({role:m.role, content:m.content}))
  │         ├─ on token → renderer.updateLiveBubble(buffer)
  │         ├─ on citation → renderer.attachCitationsToLiveBubble(cites)
  │         ├─ on done → 
  │         │     mutate(s => {
  │         │       s.chats.find(...).messages.push({
  │         │         role:'assistant', content: buffer,
  │         │         citations: currentCites, ts: Date.now()
  │         │       });
  │         │     });
  │         └─ on error → renderer.showError(data) + 不写 messages（用户可重试）
```

**新建会话**：`createChat()` → mutate push 新 chat → 切 active → re-render

**切换会话**：`switchChat(id)` → mutate 改 activeId → re-render（**不发 WS**，纯本地）

**删除会话**：`deleteChat(id)` → mutate 移除 → 若删的是 active 且还有别的 → 切到第一个；若删完 → 自动新建一个空 chat

**重命名**：双击标题或点 `⋯ → 重命名` → 标题变成 `<input>`，blur 或 Enter 提交，Esc 取消

### §5.4 Markdown 渲染（自写）

~80 行 vanilla JS，函数 `md(text) → htmlString`：
1. 先 escape HTML
2. 提取 ```fenced code``` 块 → 替换为 `<pre><code>`
3. 行内 `**bold**` `` `code` `` `[text](url)` → 对应 HTML（`<a target="_blank">`）
4. 按行扫：`# ` `## ` `### ` → `<h1/h2/h3>`；`- ` `* ` → `<ul><li>`；`>` → `<blockquote>`；空行分段
5. 输出前再做一次 link/attr 安全过滤（`javascript:` 协议剥离）

→ 不依赖第三方库；~80 行覆盖 90% 用例。

### §5.5 WS 客户端细节

- 同一时刻只允许一条 WS；新发送先 abort 旧的（`ws.close()`）再开新连接
- 单条连接超时 90s 强制关闭（兜底）
- error 文案：现在不再需要「重置会话」提示（无服务端状态了），改成「点左下角 ＋ 新会话」

---

## §6 测试策略

### §6.1 后端测试

| 文件 | 内容 |
|---|---|
| `test_chat_history.py`（新增） | WS `history` 协议：单 turn、多 turn 历史、最后一条非 user 报错、空 history、累计长度超 4000 |
| `test_chat_history_no_doc_citation.py`（新增） | 历史里含上一轮的 tool 消息 → 本轮不应重发那些 citation |
| `test_chat_history_no_checkpoint.py`（新增） | 跑两次 WS 同 `session_id`，第二次的输入完全决定性（第一次的结果不影响第二次） |
| `test_api.py`（更新） | 前端断言改成新结构（见 §6.2） |

示例：
```python
def test_chat_history_only_emits_current_turn_citations(client):
    ws1.send_json({"session_id": sid, "history": [
        {"role":"user","content":"first"}
    ]})
    events1 = collect(ws1)
    cites1 = [e for e in events1 if e["event"]=="citation"]
    assert len(cites1) == 1

    ws2.send_json({"session_id": sid, "history": [
        {"role":"user","content":"first"},
        {"role":"assistant","content":"old answer"},
        {"role":"user","content":"second"}
    ]})
    events2 = collect(ws2)
    cites2 = [e for e in events2 if e["event"]=="citation"]
    assert all(c["filename"] == "second.pdf" for c in cites2)
```

### §6.2 前端断言（仍然在 `tests/test_api.py`，无 browser）

```python
def test_frontend_uses_localstorage_for_history(client):
    app_js = client.get("/app.js").text
    assert 'localStorage.getItem("counselor:state")' in app_js
    assert 'localStorage.setItem("counselor:state"' in app_js

def test_frontend_sends_full_history_per_request(client):
    app_js = client.get("/app.js").text
    assert '"history"' in app_js or "'history'" in app_js

def test_frontend_has_sidebar_and_toggle(client):
    html = client.get("/").text
    assert 'id="sidebar"' in html
    assert 'id="sidebar-toggle"' in html

def test_frontend_cache_bust_increments(client):
    html = client.get("/").text
    m = re.search(r'app\.js\?v=(\d+)', html)
    assert int(m.group(1)) >= 5   # was 4 in prior baseline
```

不引入 Playwright（保持「纯文本断言 + 已有静态服务测试」风格），符合现有约定。

### §6.3 手动 smoke（写到 README，不算自动测试）

```bash
bash scripts/run.sh
# 浏览器开 http://localhost:8000
# 1. 看到左侧栏 + 1 个默认会话
# 2. 发消息 → 助手回复 + 引用 chip
# 3. 「＋ 新会话」 → 切到新空会话
# 4. 旧会话点回去 → 历史还在
# 5. F5 刷新 → 全部会话还在
# 6. 删掉一个会话 → 切到下一个
# 7. 关掉服务再开 → 数据全没了（确认无服务端持久化）
```

---

## §7 错误处理 / 边界

| 场景 | 行为 |
|---|---|
| localStorage 读失败（隐私模式 / 超限） | `loadState()` catch → 用内存 state（不持久化）+ 顶栏提示「数据将不会保存」 |
| localStorage 写入超限（5MB） | saveState catch → 弹 toast「存储空间不足，请删除旧会话」+ 不阻断功能 |
| `history` 为空数组 | 后端返回 `error: "empty history"` |
| `history` 最后一条 role 不是 user | 后端返回 `error: "history must end with user message"` |
| WS 断开 | UI 显示「连接中断」+ 「重试」按钮（不发新消息，避免重复） |
| 后端 agent 抛异常 | UI 把 assistant 气泡变红 + 显示错误；**不**写 messages（用户可重发）；不再提示「重置会话」（无意义） |
| 服务重启 | localStorage 完好；服务端无状态；无需任何迁移 |
| 多 tab 同时打开同一站 | **不做同步**；后写覆盖先写（极简约定，文档里写明） |
| 引用的 snippet 含 HTML | 后端 `to_citations` 已保证 snippet 是纯文本；前端渲染也 escape 双保险 |
| markdown 渲染含 `<script>` | §5.4 末段 escape 双保险 + `javascript:` 协议剥离 |

---

## §8 实施步骤（高层）

1. **后端先行**
   - `app/routes_chat.py` 改为接收 `history`，构造 messages，去 SqliteSaver
   - `agent/graph.py` 调整 `build_graph`（checkpointer 可选，默认 None）
   - `storage/paths.py` 删 `CHECKPOINT_DB`
   - 新增测试 `test_chat_history*.py`
   - 更新 `test_api.py`
2. **前端重写**
   - `web/index.html` 新骨架（sidebar + topbar + chat + input + drawer）
   - `web/style.css` 重写（CSS variables、CSS Grid 布局、移动断点）
   - `web/app.js` 重写（store / wsClient / renderer / inputCtl / sidebarCtl / chatActions / markdown）
3. **清理**
   - 启动脚本里加一次 `rm -f data/checkpoints.db`（一次性迁移）
   - `CLAUDE.md` 更新（移除 SqliteSaver 段、改前端描述）
4. **验证**
   - `OFFLINE=1 uv run --extra dev pytest` 全过
   - 浏览器手动 smoke 7 步

---

## §9 不做（明确排除）

- 用户系统、鉴权、远程托管（CLAUDE.md 已排除）
- 暗色模式（首版预留 CSS 媒体查询占位，不实现）
- markdown 完整语法（首版覆盖标题/列表/代码块/粗体/链接/行内 code）
- IndexedDB、Service Worker、PWA
- 多 tab 同步
- 拖拽上传文件、图片消息、语音输入
- 服务端统计 / 审计（仅留 `session_id` hook）

---

## §10 验收标准

- [ ] 所有现有测试 (`OFFLINE=1 uv run --extra dev pytest`) 通过
- [ ] 新增后端测试（`test_chat_history*.py`）全部通过
- [ ] 前端断言（`test_api.py` 新增 4 条）通过
- [ ] 浏览器 smoke 7 步全过
- [ ] 重启服务后客户端数据完好（localStorage 验证）
- [ ] CLAUDE.md 已更新（删除 SqliteSaver 相关描述，描述新前端结构）
- [ ] README 已更新（删除旧的「重置会话」提示段落，描述多会话流程）