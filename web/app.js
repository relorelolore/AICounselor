"use strict";
// ============================================================================
// AI 辅导员 — multi-session client. All persistence is in localStorage; the
// server is stateless and receives the full history on every WS frame.
// ============================================================================

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// ---------- Constants & utils ----------
const STORAGE_KEY = "counselor:state";
const STATE_VERSION = 1;
const MAX_TITLE_LEN = 24;
const MAX_MESSAGE_CHARS = 4000;
const MAX_HISTORY_CHARS = 4000 * 20;
const MAX_TITLE_PREFIX = (n) => `${n}/4000`;

function uuidv4() {
  if (typeof crypto !== "undefined") {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    if (typeof crypto.getRandomValues === "function") {
      const b = crypto.getRandomValues(new Uint8Array(16));
      b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
      const h = []; for (let i = 0; i < 16; i++) h.push(b[i].toString(16).padStart(2, "0"));
      return `${h.slice(0,4).join("")}-${h.slice(4,6).join("")}-${h.slice(6,8).join("")}-${h.slice(8,10).join("")}-${h.slice(10,16).join("")}`;
    }
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function formatRelativeTime(ts) {
  const diff = Date.now() - ts;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  const d = new Date(ts);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(ts); day.setHours(0, 0, 0, 0);
  if (day.getTime() === today.getTime()) return d.toTimeString().slice(0, 5);
  if (day.getTime() === today.getTime() - 86_400_000) return "昨天";
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function autoTitle(text) {
  const t = String(text || "").trim().replace(/\s+/g, " ");
  if (!t) return "新会话";
  return t.length > MAX_TITLE_LEN ? t.slice(0, MAX_TITLE_LEN) + "…" : t;
}

let _toastTimer = null;
function toast(text) {
  const el = $("#toast"); if (!el) return;
  const t = $("#toast-text"); if (t) t.textContent = text;
  el.hidden = false;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.hidden = true; }, 2500);
}

async function fetchWithTimeout(url, options = {}, ms = 3000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try { return await fetch(url, { ...options, signal: ctrl.signal }); }
  finally { clearTimeout(t); }
}

// ---------- Store ----------
function blankChat() {
  const now = Date.now();
  return { id: uuidv4(), title: "新会话", createdAt: now, updatedAt: now, messages: [] };
}

function blankState() {
  const c = blankChat();
  return { version: STATE_VERSION, activeId: c.id, chats: [c] };
}

const store = {
  state: blankState(),
  _listeners: [],
  _loadFailed: false,
  load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) { this.state = blankState(); return this.state; }
      const parsed = JSON.parse(raw);
      if (parsed && parsed.version === STATE_VERSION && Array.isArray(parsed.chats) && parsed.chats.length > 0) {
        // Validate each chat has the required fields; drop broken ones.
        parsed.chats = parsed.chats.filter((c) =>
          c && typeof c.id === "string" && Array.isArray(c.messages) &&
          typeof c.title === "string" && typeof c.createdAt === "number"
        );
        if (parsed.chats.length === 0) {
          const fresh = blankChat();
          parsed.chats = [fresh]; parsed.activeId = fresh.id;
        }
        if (!parsed.chats.find((c) => c.id === parsed.activeId)) parsed.activeId = parsed.chats[0].id;
        this.state = parsed;
      } else {
        this.state = blankState();
      }
    } catch (e) {
      console.warn("[store] load failed; using in-memory only:", e);
      this._loadFailed = true;
      this.state = blankState();
    }
    return this.state;
  },
  save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.state));
    } catch (e) {
      console.warn("[store] save failed:", e);
      toast("存储空间不足，请删除旧会话");
    }
  },
  mutate(fn) {
    fn(this.state);
    this.save();
    for (const l of this._listeners) l(this.state);
  },
  onChange(fn) { this._listeners.push(fn); return () => { this._listeners = this._listeners.filter((l) => l !== fn); }; },
  active() { return this.state.chats.find((c) => c.id === this.state.activeId) || this.state.chats[0]; },
};

// ---------- WS client ----------
const wsClient = {
  _ws: null,
  connect(history, handlers) {
    // Abort any existing connection first.
    if (this._ws) { try { this._ws.close(); } catch {} this._ws = null; }
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/ws/chat`;
    const sessionId = store.active()?.id || uuidv4();
    const ws = new WebSocket(url);
    this._ws = ws;
    const sendTimer = setTimeout(() => {
      try { ws.close(); } catch {}
      handlers.onError("连接超时（90s）");
    }, 90_000);
    ws.onopen = () => {
      try {
        ws.send(JSON.stringify({ session_id: sessionId, history }));
      } catch (e) {
        handlers.onError("发送失败：" + e);
        try { ws.close(); } catch {}
      }
    };
    ws.onmessage = (ev) => {
      let payload; try { payload = JSON.parse(ev.data); } catch { return; }
      if (payload.event === "token") handlers.onToken(payload.data || "");
      else if (payload.event === "citation") handlers.onCitation(payload.data || []);
      else if (payload.event === "done") { clearTimeout(sendTimer); handlers.onDone(); }
      else if (payload.event === "error") { clearTimeout(sendTimer); handlers.onError(payload.data || "未知错误"); }
    };
    ws.onerror = () => { clearTimeout(sendTimer); handlers.onError("WebSocket 连接失败"); };
    ws.onclose = () => { clearTimeout(sendTimer); if (this._ws === ws) this._ws = null; };
    return { abort: () => { try { ws.close(); } catch {} } };
  },
};

// ---------- Markdown (minimal safe renderer) ----------
function md(text) {
  if (!text) return "";
  // 1. Escape first.
  let s = escapeHtml(text);
  // 2. Fenced code blocks ```lang\n...\n```
  s = s.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${escapeHtml(lang)}">${code}</code></pre>`);
  // 3. Inline code `code`
  s = s.replace(/`([^`\n]+)`/g, (_, code) => `<code>${code}</code>`);
  // 4. Bold **text**
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  // 5. Links [text](url) — strip dangerous protocols.
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, t, u) => {
    const safe = /^(https?:|mailto:|#|\/)/i.test(u.trim()) ? u : "#";
    return `<a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${t}</a>`;
  });
  // 6. Block-level: split on blank lines, then per-line scan.
  const blocks = s.split(/\n{2,}/);
  return blocks.map((block) => {
    const lines = block.split("\n");
    // Headings
    if (lines.every((l) => /^### /.test(l))) return "<h3>" + lines.map((l) => l.slice(4)).join("<br>") + "</h3>";
    if (lines.every((l) => /^## /.test(l))) return "<h2>" + lines.map((l) => l.slice(3)).join("<br>") + "</h2>";
    if (lines.every((l) => /^# /.test(l))) return "<h1>" + lines.map((l) => l.slice(2)).join("<br>") + "</h1>";
    // Unordered list
    if (lines.every((l) => /^[-*] /.test(l))) {
      return "<ul>" + lines.map((l) => `<li>${l.slice(2)}</li>`).join("") + "</ul>";
    }
    // Ordered list
    if (lines.every((l) => /^\d+\. /.test(l))) {
      return "<ol>" + lines.map((l) => `<li>${l.replace(/^\d+\. /, "")}</li>`).join("") + "</ol>";
    }
    // Blockquote
    if (lines.every((l) => /^> /.test(l))) return "<blockquote>" + lines.map((l) => l.slice(2)).join("<br>") + "</blockquote>";
    // Paragraph with inline newlines → <br>
    return "<p>" + lines.join("<br>") + "</p>";
  }).join("");
}

// ============================================================================
// Renderer
// ============================================================================
const renderer = {
  init() {
    store.onChange(() => this.renderAll());
  },
  renderAll() {
    this.renderSidebar();
    this.renderChat();
  },

  // -- Sidebar --
  renderSidebar() {
    const list = $("#chat-list"); if (!list) return;
    const chats = [...store.state.chats].sort((a, b) => b.updatedAt - a.updatedAt);
    // Group by updatedAt bucket.
    const today0 = new Date(); today0.setHours(0, 0, 0, 0);
    const yesterday0 = new Date(today0.getTime() - 86_400_000);
    const week0 = new Date(today0.getTime() - 6 * 86_400_000);
    const groups = { 今天: [], 昨天: [], 本周: [], 更早: [] };
    for (const c of chats) {
      const t = new Date(c.updatedAt); t.setHours(0, 0, 0, 0);
      if (t.getTime() >= today0.getTime()) groups["今天"].push(c);
      else if (t.getTime() >= yesterday0.getTime()) groups["昨天"].push(c);
      else if (t.getTime() >= week0.getTime()) groups["本周"].push(c);
      else groups["更早"].push(c);
    }
    const frag = document.createDocumentFragment();
    for (const [name, arr] of Object.entries(groups)) {
      if (arr.length === 0) continue;
      const h = document.createElement("div");
      h.className = "chat-group-title"; h.textContent = name;
      frag.appendChild(h);
      for (const c of arr) {
        const item = document.createElement("div");
        item.className = "chat-item" + (c.id === store.state.activeId ? " active" : "");
        item.dataset.id = c.id;
        const t = document.createElement("span");
        t.className = "chat-title-text"; t.textContent = c.title;
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "chat-menu-btn"; btn.textContent = "⋯";
        btn.title = "更多";
        btn.dataset.act = "menu";
        item.appendChild(t); item.appendChild(btn);
        frag.appendChild(item);
      }
    }
    list.replaceChildren(frag);
  },

  // -- Topbar --
  renderTopbar() {
    const titleEl = $("#chat-title"); if (!titleEl) return;
    titleEl.textContent = store.active()?.title || "新会话";
  },

  // -- Chat --
  renderChat() {
    const msgsEl = $("#messages"); const emptyEl = $("#empty-state");
    if (!msgsEl || !emptyEl) return;
    this.renderTopbar();
    const chat = store.active();
    if (!chat || chat.messages.length === 0) {
      msgsEl.replaceChildren();
      emptyEl.hidden = false;
      return;
    }
    emptyEl.hidden = true;
    const frag = document.createDocumentFragment();
    const tpl = $("#message-template");
    for (const m of chat.messages) {
      const node = tpl.content.firstElementChild.cloneNode(true);
      this._fillMessage(node, m);
      frag.appendChild(node);
    }
    msgsEl.replaceChildren(frag);
    msgsEl.scrollTop = msgsEl.scrollHeight;
  },
  _fillMessage(node, m) {
    node.classList.add(m.role);
    const content = $(".msg-content", node);
    if (m.role === "assistant") content.innerHTML = md(m.content || "");
    else content.textContent = m.content || "";
    const cites = $(".msg-cites", node);
    if (m.role === "assistant" && Array.isArray(m.citations) && m.citations.length > 0) {
      cites.hidden = false;
      cites.replaceChildren(...m.citations.map((c, i) => {
        const b = document.createElement("button");
        b.type = "button"; b.textContent = `引 ${i + 1}`;
        b.dataset.citeIdx = String(i);
        return b;
      }));
    }
  },

  // -- Live assistant bubble (during streaming) --
  appendLiveBubble() {
    const msgsEl = $("#messages"); const tpl = $("#message-template");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.classList.add("assistant", "thinking");
    node.dataset.live = "1";
    $(".msg-content", node).textContent = "";
    msgsEl.appendChild(node);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    return {
      setToken: (s) => {
        const c = $(".msg-content", node);
        c.textContent = s;
        msgsEl.scrollTop = msgsEl.scrollHeight;
      },
      setCitations: (cites) => {
        const citesEl = $(".msg-cites", node);
        if (!cites || cites.length === 0) { citesEl.hidden = true; return; }
        citesEl.hidden = false;
        citesEl.replaceChildren(...cites.map((c, i) => {
          const b = document.createElement("button");
          b.type = "button"; b.textContent = `引 ${i + 1}`;
          b.dataset.citeIdx = String(i); b.dataset.live = "1";
          return b;
        }));
      },
      finish: () => {
        node.classList.remove("thinking");
        const live = $$("[data-live='1']", node); live.forEach((el) => delete el.dataset.live);
      },
      showError: (msg) => {
        node.classList.remove("thinking"); node.classList.add("error");
        $(".msg-content", node).textContent = "（出错了）" + msg;
        const live = $$("[data-live='1']", node); live.forEach((el) => delete el.dataset.live);
      },
    };
  },
};

// ============================================================================
// Chat actions
// ============================================================================
const chatActions = {
  create() {
    store.mutate((s) => {
      const c = blankChat();
      s.chats.push(c); s.activeId = c.id;
    });
  },
  switchTo(id) {
    if (!store.state.chats.find((c) => c.id === id)) return;
    store.mutate((s) => { s.activeId = id; });
  },
  rename(id, newTitle) {
    const t = String(newTitle || "").trim();
    if (!t) return;
    store.mutate((s) => {
      const c = s.chats.find((x) => x.id === id); if (c) { c.title = t; c.updatedAt = Date.now(); }
    });
  },
  remove(id) {
    store.mutate((s) => {
      s.chats = s.chats.filter((c) => c.id !== id);
      if (s.chats.length === 0) { const c = blankChat(); s.chats.push(c); }
      if (id === s.activeId) s.activeId = s.chats[0].id;
    });
  },
  clearAll() {
    store.mutate((s) => {
      const c = blankChat();
      s.chats = [c]; s.activeId = c.id;
    });
  },
  async send(text) {
    const t = String(text || "").trim();
    if (!t || t.length > MAX_MESSAGE_CHARS) return;
    const chat = store.active(); if (!chat) return;
    // Push user message + auto-title if needed.
    store.mutate((s) => {
      const c = s.chats.find((x) => x.id === s.activeId);
      c.messages.push({ role: "user", content: t, ts: Date.now() });
      c.updatedAt = Date.now();
      if (c.title === "新会话") c.title = autoTitle(t);
    });
    renderer.renderChat();
    // Build history from current chat (drop tool messages).
    const history = chat.messages
      .filter((m) => m.role !== "tool")
      .map((m) => ({ role: m.role, content: m.content || "" }));
    const live = renderer.appendLiveBubble();
    let buffer = ""; let cites = [];
    wsClient.connect(history, {
      onToken: (chunk) => { buffer += chunk; live.setToken(buffer); },
      onCitation: (c) => { cites = c; live.setCitations(c); },
      onDone: () => {
        live.finish();
        store.mutate((s) => {
          const c = s.chats.find((x) => x.id === s.activeId);
          c.messages.push({ role: "assistant", content: buffer, citations: cites, ts: Date.now() });
          c.updatedAt = Date.now();
        });
      },
      onError: (msg) => {
        live.showError(msg);
        // Don't push the assistant message — user can retry.
      },
    });
  },
};

// ============================================================================
// Controller glue
// ============================================================================
const inputCtl = {
  init() {
    const input = $("#input"); const send = $("#send"); const count = $("#char-count");
    if (!input || !send || !count) return;
    const submit = () => {
      const v = input.value;
      if (!v.trim()) return;
      input.value = ""; count.textContent = "0"; input.style.height = "auto";
      chatActions.send(v);
    };
    const autoSize = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; };
    input.addEventListener("input", () => { count.textContent = String(input.value.length); autoSize(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    });
    send.addEventListener("click", submit);
  },
};

const sidebarCtl = {
  init() {
    const list = $("#chat-list"); const toggle = $("#sidebar-toggle");
    const toggleInline = $("#sidebar-toggle-inline");
    const newBtn = $("#new-chat-btn");
    const setCollapsed = (collapsed) => {
      document.body.classList.toggle("sidebar-collapsed", collapsed);
      try { localStorage.setItem("counselor:sidebar-collapsed", collapsed ? "1" : "0"); } catch {}
    };
    if (toggle) toggle.addEventListener("click", () => {
      const collapsed = !document.body.classList.contains("sidebar-collapsed");
      setCollapsed(collapsed);
    });
    if (toggleInline) toggleInline.addEventListener("click", () => setCollapsed(false));
    if (newBtn) newBtn.addEventListener("click", () => { chatActions.create(); });
    if (list) list.addEventListener("click", (e) => {
      const item = e.target.closest(".chat-item"); if (!item) return;
      const id = item.dataset.id;
      if (e.target.dataset.act === "menu") {
        const rect = item.getBoundingClientRect();
        openContextMenu(id, rect.left, rect.bottom);
        return;
      }
      chatActions.switchTo(id);
    });
    // Restore collapsed state.
    try {
      if (localStorage.getItem("counselor:sidebar-collapsed") === "1") setCollapsed(true);
    } catch {}
  },
};

const topbarCtl = {
  init() {
    const titleEl = $("#chat-title"); const inputEl = $("#chat-title-input");
    const commit = () => {
      const newTitle = inputEl.value.trim();
      inputEl.hidden = true; titleEl.hidden = false;
      if (newTitle) chatActions.rename(store.active().id, newTitle);
      else renderer.renderTopbar();
    };
    const cancel = () => { inputEl.hidden = true; titleEl.hidden = false; };
    const beginEdit = () => {
      inputEl.value = store.active().title;
      inputEl.hidden = false; titleEl.hidden = true;
      inputEl.focus(); inputEl.select();
    };
    if (titleEl) titleEl.addEventListener("click", beginEdit);
    if (titleEl) titleEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); beginEdit(); } });
    if (inputEl) {
      inputEl.addEventListener("blur", commit);
      inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); commit(); }
        else if (e.key === "Escape") { e.preventDefault(); cancel(); }
      });
    }
    // Actions menu
    const btn = $("#chat-actions-btn"); const menu = $("#chat-actions-menu");
    if (btn && menu) {
      btn.addEventListener("click", (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; });
      document.addEventListener("click", () => { menu.hidden = true; });
      menu.addEventListener("click", (e) => {
        const act = e.target.dataset.act; if (!act) return;
        menu.hidden = true;
        if (act === "rename") { beginEdit(); }
        else if (act === "delete") {
          if (confirm("删除当前会话？此操作不可撤销。")) chatActions.remove(store.active().id);
        }
        else if (act === "clear-all") {
          if (confirm("清空全部会话？此操作不可撤销。")) chatActions.clearAll();
        }
      });
    }
    // Reindex
    const reindexBtn = $("#reindex");
    if (reindexBtn) reindexBtn.addEventListener("click", async () => {
      reindexBtn.disabled = true; reindexBtn.textContent = "处理中…";
      try {
        const r = await fetchWithTimeout("/api/ingest", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ force: false }),
        }, 30000);
        const data = await r.json();
        toast(`索引完成：新增 ${data.added}，跳过 ${data.skipped}，失败 ${data.failed.length}`);
        refreshHealth();
      } catch (e) { toast("入索引失败：" + e); }
      finally { reindexBtn.disabled = false; reindexBtn.textContent = "重建索引"; }
    });
  },
};

// Citation drawer
const drawerCtl = {
  init() {
    const drawer = $("#drawer"); const body = $("#drawer-body"); const close = $("#drawer-close"); const backdrop = $("#drawer-backdrop");
    const closeDrawer = () => { drawer.hidden = true; backdrop.hidden = true; body.replaceChildren(); };
    if (close) close.addEventListener("click", closeDrawer);
    if (backdrop) backdrop.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !drawer.hidden) closeDrawer(); });
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".msg-cites button[data-cite-idx]"); if (!btn) return;
      const idx = Number(btn.dataset.citeIdx);
      const chat = store.active();
      // Find the message that contains this button (rendered or live).
      let m = chat?.messages.find((x) => x.role === "assistant" && Array.isArray(x.citations) && x.citations[idx]);
      if (!m) {
        const liveNode = document.querySelector(".msg.assistant.thinking, .msg.assistant");
        const liveCites = liveNode ? $$(".msg-cites button[data-cite-idx]", liveNode) : [];
        const liveIdx = liveCites.indexOf(btn);
        if (liveIdx >= 0) m = _liveCitations[liveIdx] && { citations: _liveCitations };
      }
      if (!m || !m.citations || !m.citations[idx]) return;
      const c = m.citations[idx];
      body.replaceChildren();
      const card = document.createElement("div");
      card.className = "drawer-cite";
      const head = document.createElement("div"); head.className = "cite-head"; head.textContent = `《${c.filename}》 第 ${c.page} 页`;
      const snip = document.createElement("div"); snip.className = "cite-snippet"; snip.textContent = c.snippet || "";
      card.appendChild(head); card.appendChild(snip); body.appendChild(card);
      drawer.hidden = false; backdrop.hidden = false;
    });
  },
};
// Track live citation array so drawer can resolve before store commit.
const _liveCitations = [];

// Empty state new button
const emptyCtl = {
  init() {
    const btn = $("#empty-state-new"); if (btn) btn.addEventListener("click", () => chatActions.create());
  },
};

// Context menu for chat items (simple confirm-based; reuse window.confirm to avoid new UI)
function openContextMenu(id, x, y) {
  const c = store.state.chats.find((x) => x.id === id); if (!c) return;
  const choice = prompt(`操作「${c.title}」：\n1. 重命名\n2. 删除\n输入 1 或 2：`);
  if (choice === "1") {
    const t = prompt("新标题：", c.title);
    if (t && t.trim()) chatActions.rename(id, t.trim());
  } else if (choice === "2") {
    if (confirm("删除这个会话？")) chatActions.remove(id);
  }
}

// ---------- Health probe ----------
let _healthDot = null, _healthText = null;
async function refreshHealth() {
  if (!_healthDot) { _healthDot = $("#status-dot"); _healthText = $("#status-text"); }
  try {
    const r = await fetchWithTimeout("/api/health", {}, 3000);
    const data = await r.json();
    const ok = data.status === "ok";
    _healthDot.classList.toggle("ok", ok);
    _healthDot.classList.toggle("degraded", !ok);
    _healthText.textContent = ok ? "在线" : (data.llm ? "索引未建立" : "模型未连接");
  } catch (e) {
    _healthDot.classList.remove("ok"); _healthDot.classList.add("degraded");
    _healthText.textContent = e.name === "AbortError" ? "连接超时" : "无法连接后端";
  }
}

// ---------- Boot ----------
function boot() {
  store.load();
  if (store._loadFailed) toast("数据无法从本地加载，仅本次会话可用");
  renderer.init();
  sidebarCtl.init();
  topbarCtl.init();
  inputCtl.init();
  drawerCtl.init();
  emptyCtl.init();
  renderer.renderAll();
  refreshHealth();
  setInterval(refreshHealth, 30000);
}

boot();
