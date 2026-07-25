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

// ---------- Boot (placeholder — Task 5 wires the rest) ----------
function boot() {
  store.load();
  if (store._loadFailed) toast("数据无法从本地加载，仅本次会话可用");
}

boot();
