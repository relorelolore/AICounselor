const $ = (sel) => document.querySelector(sel);

const messagesEl = $("#messages");
const inputEl = $("#input");
const sendEl = $("#send");
const charCount = $("#char-count");
const statusDot = $("#status-dot");
const statusText = $("#status-text");
const reindexEl = $("#reindex");
const resetSessionEl = $("#reset-session");
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

async function fetchWithTimeout(url, options = {}, ms = 3000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...options, signal: ctrl.signal });
  } finally {
    clearTimeout(t);
  }
}

async function refreshHealth() {
  try {
    const r = await fetchWithTimeout("/api/health", {}, 3000);
    const data = await r.json();
    const ok = data.status === "ok";
    statusDot.classList.toggle("ok", ok);
    statusDot.classList.toggle("degraded", !ok);
    statusText.textContent = ok ? "在线" : (data.llm ? "索引未建立" : "模型未连接");
  } catch (e) {
    statusDot.classList.remove("ok");
    statusDot.classList.add("degraded");
    if (e.name === "AbortError") {
      statusText.textContent = "连接超时";
    } else {
      statusText.textContent = "无法连接后端";
    }
  }
}

async function reindex() {
  reindexEl.disabled = true;
  reindexEl.textContent = "处理中…";
  try {
    const r = await fetchWithTimeout("/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: false }),
    }, 30000);
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
      const data = payload.data || "";
      const hint = data.startsWith("agent error:") || data.startsWith("agent error (") || data.startsWith("unexpected:")
        ? "\n\n（提示：可点右上角「重置会话」恢复，或请管理员清空 data/ 目录）"
        : "";
      assistantEl.textContent = "（出错了）" + data + hint;
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
resetSessionEl.addEventListener("click", () => {
  if (confirm("确定要清空当前会话并重新开始吗？")) {
    localStorage.removeItem("session_id");
    location.reload();
  }
});

refreshHealth();
setInterval(refreshHealth, 30000);