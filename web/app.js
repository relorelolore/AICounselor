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
const SIDEBAR_COLLAPSED_KEY = "counselor:sidebar-collapsed";
const MAX_TITLE_LEN = 24;
const MAX_MESSAGE_CHARS = 4000;

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
        const text = document.createElement("div");
        text.className = "chat-text";
        const t = document.createElement("span");
        t.className = "chat-title-text"; t.textContent = c.title;
        const time = document.createElement("span");
        time.className = "chat-time"; time.textContent = formatRelativeTime(c.updatedAt);
        text.appendChild(t); text.appendChild(time);
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "chat-menu-btn"; btn.textContent = "⋯";
        btn.title = "更多";
        btn.dataset.act = "menu";
        item.appendChild(text); item.appendChild(btn);
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
    for (const [idx, m] of chat.messages.entries()) {
      const node = tpl.content.firstElementChild.cloneNode(true);
      this._fillMessage(node, m, idx);
      frag.appendChild(node);
    }
    msgsEl.replaceChildren(frag);
    msgsEl.scrollTop = msgsEl.scrollHeight;
  },
  _fillMessage(node, m, msgIdx) {
    node.classList.add(m.role);
    node.dataset.msgIdx = String(msgIdx);
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
    node.dataset.liveMsg = "1";
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
        delete node.dataset.live;
        const live = $$("[data-live='1']", node); live.forEach((el) => delete el.dataset.live);
      },
      showError: (msg) => {
        node.classList.remove("thinking"); node.classList.add("error");
        delete node.dataset.live;
        $(".msg-content", node).textContent = "（出错了）" + msg;
        const live = $$("[data-live='1']", node); live.forEach((el) => delete el.dataset.live);
      },
    };
  },
};

// ============================================================================
// Chat actions
// ============================================================================
let _liveCitationsForActiveSend = null;
let currentLive = null;
function setStopVisible(visible) {
  const stop = $("#stop"); const send = $("#send");
  if (stop) stop.hidden = !visible;
  if (send) send.hidden = visible;
}
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
    const targetChatId = chat.id;
    // A new send supersedes any still-streaming response from the previous send.
    if (currentLive) {
      currentLive.showError("（已取消）");
      currentLive = null;
      _liveCitationsForActiveSend = null;
    }
    setStopVisible(true);
    // Push user message + auto-title if needed.
    store.mutate((s) => {
      const c = s.chats.find((x) => x.id === targetChatId);
      if (!c) return;
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
    currentLive = live;
    _liveCitationsForActiveSend = null;
    let buffer = ""; let cites = [];
    wsClient.connect(history, {
      onToken: (chunk) => {
        if (currentLive !== live) return;
        buffer += chunk; live.setToken(buffer);
      },
      onCitation: (c) => {
        if (currentLive !== live) return;
        cites = c; _liveCitationsForActiveSend = c; live.setCitations(c);
      },
      onDone: () => {
        if (currentLive !== live) return;
        live.finish();
        currentLive = null;
        _liveCitationsForActiveSend = null;
        setStopVisible(false);
        store.mutate((s) => {
          const c = s.chats.find((x) => x.id === targetChatId);
          if (!c) return;
          c.messages.push({ role: "assistant", content: buffer, citations: cites, ts: Date.now() });
          c.updatedAt = Date.now();
        });
      },
      onError: (msg) => {
        if (currentLive !== live) return;
        live.showError(msg);
        currentLive = null;
        _liveCitationsForActiveSend = null;
        setStopVisible(false);
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
    const stop = $("#stop");
    if (stop) stop.addEventListener("click", () => {
      // Close the active WS; onclose → onDone fires with whatever has been
      // buffered. If nothing yet, the bubble flips to error state in chatActions.
      if (wsClient._ws) { try { wsClient._ws.close(); } catch {} }
    });
  },
};

const sidebarCtl = {
  init() {
    const list = $("#chat-list"); const toggle = $("#sidebar-toggle");
    const toggleInline = $("#sidebar-toggle-inline");
    const newBtn = $("#new-chat-btn");
    const isDesktop = () => window.matchMedia("(min-width: 769px)").matches;
    const setCollapsed = (collapsed) => {
      document.body.classList.toggle("sidebar-collapsed", collapsed);
      if (toggleInline) toggleInline.hidden = !collapsed;
      try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0"); } catch {}
    };
    // Restore persisted preference; default = expanded (no collapse) on desktop,
    // collapsed (hidden) on mobile.
    let stored = null;
    try { stored = localStorage.getItem(SIDEBAR_COLLAPSED_KEY); } catch {}
    if (stored === "1" || stored === "0") setCollapsed(stored === "1");
    else setCollapsed(!isDesktop());
    const toggleHandler = () => {
      const collapsed = document.body.classList.contains("sidebar-collapsed");
      setCollapsed(!collapsed);
    };
    if (toggle) toggle.addEventListener("click", toggleHandler);
    if (toggleInline) toggleInline.addEventListener("click", toggleHandler);
    // On mobile, switch to a chat should close the sidebar overlay so the
    // user can see the chat content. On desktop the sidebar stays open.
    if (list) list.addEventListener("click", (e) => {
      const item = e.target.closest(".chat-item"); if (!item) return;
      const id = item.dataset.id;
      if (e.target.dataset.act === "menu") {
        openContextMenu(id);
        return;
      }
      chatActions.switchTo(id);
      if (!isDesktop()) setCollapsed(true);
    });
    // When the viewport shrinks below the breakpoint, auto-collapse (hide).
    window.matchMedia("(min-width: 769px)").addEventListener?.("change", (e) => {
      if (!e.matches) setCollapsed(true);
    });
    if (newBtn) newBtn.addEventListener("click", () => { chatActions.create(); });
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
      menu.addEventListener("click", async (e) => {
        const act = e.target.dataset.act; if (!act) return;
        menu.hidden = true;
        if (act === "rename") { beginEdit(); }
        else if (act === "delete") {
          const ok = await modalCtl.confirm({
            title: "删除当前会话？",
            message: `「${store.active().title}」将被永久删除，无法撤销。`,
            confirmLabel: "删除",
            danger: true,
          });
          if (ok) chatActions.remove(store.active().id);
        }
        else if (act === "clear-all") {
          const ok = await modalCtl.confirm({
            title: "清空全部会话？",
            message: `所有 ${store.state.chats.length} 个会话将被永久删除，无法撤销。`,
            confirmLabel: "全部删除",
            danger: true,
          });
          if (ok) chatActions.clearAll();
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
      const msgNode = btn.closest(".msg");
      let m = null;
      if (msgNode?.dataset.liveMsg === "1") {
        if (Array.isArray(_liveCitationsForActiveSend)) m = { citations: _liveCitationsForActiveSend };
      } else {
        const msgIdx = Number(msgNode?.dataset.msgIdx);
        if (Number.isInteger(msgIdx) && msgIdx >= 0) {
          const candidate = chat?.messages[msgIdx];
          if (candidate?.role === "assistant") m = candidate;
        }
      }
      if (!m || !Array.isArray(m.citations) || !m.citations[idx]) return;
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

// Empty state new button
const emptyCtl = {
  init() {
    const btn = $("#empty-state-new"); if (btn) btn.addEventListener("click", () => chatActions.create());
  },
};

// ============================================================================
// Modal dialog (replaces window.confirm / window.prompt)
// ============================================================================
const modalCtl = {
  _resolve: null,
  _kind: null,            // "confirm" | "prompt" | "choose"
  _options: null,         // for "choose"
  _backdropEl: null,
  _modalEl: null,
  _titleEl: null,
  _msgEl: null,
  _inputEl: null,
  _actionsEl: null,
  _confirmBtn: null,
  _cancelBtn: null,
  _lastFocus: null,
  init() {
    this._backdropEl = $("#modal-backdrop");
    this._modalEl = $("#modal");
    this._titleEl = $("#modal-title");
    this._msgEl = $("#modal-message");
    this._inputEl = $("#modal-input");
    this._actionsEl = $(".modal-actions", this._modalEl);
    this._confirmBtn = $("#modal-confirm");
    this._cancelBtn = $("#modal-cancel");
    const close = (result) => this._close(result);
    this._confirmBtn.addEventListener("click", () => close("confirm"));
    this._cancelBtn.addEventListener("click", () => close("cancel"));
    this._backdropEl.addEventListener("click", () => close("cancel"));
    this._inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); close("confirm"); }
      else if (e.key === "Escape") { e.preventDefault(); close("cancel"); }
    });
    document.addEventListener("keydown", (e) => {
      if (this._modalEl.hidden) return;
      if (e.key === "Escape") { e.preventDefault(); close("cancel"); }
    });
  },
  _open(kind, { title, message, defaultValue = "", placeholder = "", options = [], confirmLabel = "确认", cancelLabel = "取消", danger = false }) {
    // If another modal is open, resolve it as cancel first.
    if (!this._modalEl.hidden) this._close("cancel");
    this._lastFocus = document.activeElement;
    this._kind = kind;
    this._options = options;
    this._titleEl.textContent = title || "";
    this._msgEl.textContent = message || "";
    this._msgEl.hidden = !message;
    this._inputEl.hidden = kind !== "prompt";
    this._inputEl.value = defaultValue;
    this._inputEl.placeholder = placeholder || "";
    this._confirmBtn.textContent = confirmLabel;
    this._cancelBtn.textContent = cancelLabel;
    this._confirmBtn.classList.toggle("danger", !!danger);
    this._confirmBtn.classList.toggle("primary", !danger);
    // Render any extra option buttons (for "choose" kind) between cancel & confirm.
    this._actionsEl.replaceChildren(this._cancelBtn, this._confirmBtn);
    if (kind === "choose" && options.length > 0) {
      const extra = document.createDocumentFragment();
      options.forEach((opt, i) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = opt.label;
        b.className = opt.danger ? "danger" : "primary";
        b.dataset.choiceIdx = String(i);
        b.addEventListener("click", () => this._close({ choiceIdx: i }));
        extra.appendChild(b);
      });
      this._actionsEl.insertBefore(extra, this._cancelBtn);
    }
    this._backdropEl.hidden = false;
    this._modalEl.hidden = false;
    return new Promise((resolve) => { this._resolve = resolve; });
  },
  _close(result) {
    if (this._modalEl.hidden) return;
    const r = this._resolve; this._resolve = null;
    this._backdropEl.hidden = true;
    this._modalEl.hidden = true;
    let value = null;
    if (result === "confirm") {
      value = this._kind === "prompt" ? (this._inputEl.value || "") : true;
    } else if (result === "cancel") {
      value = this._kind === "prompt" ? null : false;
    } else if (result && typeof result === "object" && "choiceIdx" in result) {
      value = this._options[result.choiceIdx]?.value;
    }
    if (this._lastFocus && this._lastFocus.focus) try { this._lastFocus.focus(); } catch {}
    if (r) r(value);
  },
  confirm(opts) { return this._open("confirm", opts); },
  prompt(opts) { return this._open("prompt", opts); },
  choose(opts) { return this._open("choose", opts); },
};

// Per-chat sidebar action menu (replaces the native prompt/confirm flow).
async function openContextMenu(id) {
  const c = store.state.chats.find((x) => x.id === id); if (!c) return;
  const choice = await modalCtl.choose({
    title: "操作会话",
    message: `「${c.title}」`,
    options: [
      { label: "重命名", value: "rename" },
      { label: "删除",   value: "delete", danger: true },
    ],
    confirmLabel: "取消",
    cancelLabel: "取消",
  });
  if (choice === "rename") {
    const t = await modalCtl.prompt({
      title: "重命名会话",
      message: `给「${c.title}」起个新名字：`,
      defaultValue: c.title,
      placeholder: "会话标题",
      confirmLabel: "保存",
    });
    if (t && t.trim()) chatActions.rename(id, t.trim());
  } else if (choice === "delete") {
    const ok = await modalCtl.confirm({
      title: "删除会话？",
      message: `「${c.title}」将被永久删除，无法撤销。`,
      confirmLabel: "删除",
      danger: true,
    });
    if (ok) chatActions.remove(id);
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
  modalCtl.init();
  emptyCtl.init();
  renderer.renderAll();
  refreshHealth();
  setInterval(refreshHealth, 30000);
}

boot();
