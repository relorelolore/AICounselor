// ============================================================================
// 会话 store：多会话 CRUD + localStorage 持久化 + 流式回答。
// 持久化结构与旧前端完全兼容（localStorage["counselor:state"]，version 1），
// 老用户刷新后历史会话原样保留。
// ============================================================================

import { defineStore } from "pinia";

import { connectChatWs, type ChatWsConnection } from "../api/ws";
import type { Chat, ChatMessage, Citation, PersistedState, StreamingState } from "../types";
import { autoTitle, MAX_MESSAGE_CHARS, uuidv4 } from "../utils/format";

export const STORAGE_KEY = "counselor:state";
const STATE_VERSION = 1 as const;

function blankChat(): Chat {
  const now = Date.now();
  return { id: uuidv4(), title: "新会话", createdAt: now, updatedAt: now, messages: [] };
}

function blankState(): PersistedState {
  const c = blankChat();
  return { version: STATE_VERSION, activeId: c.id, chats: [c] };
}

/** 读取并校验 localStorage；损坏/缺字段时回退到全新状态。 */
function loadPersisted(): { state: PersistedState; loadFailed: boolean } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { state: blankState(), loadFailed: false };
    const parsed = JSON.parse(raw) as PersistedState;
    if (
      parsed &&
      parsed.version === STATE_VERSION &&
      Array.isArray(parsed.chats) &&
      parsed.chats.length > 0
    ) {
      parsed.chats = parsed.chats.filter(
        (c) =>
          c &&
          typeof c.id === "string" &&
          Array.isArray(c.messages) &&
          typeof c.title === "string" &&
          typeof c.createdAt === "number",
      );
      if (parsed.chats.length === 0) {
        const fresh = blankChat();
        parsed.chats = [fresh];
        parsed.activeId = fresh.id;
      }
      if (!parsed.chats.find((c) => c.id === parsed.activeId)) {
        parsed.activeId = parsed.chats[0].id;
      }
      return { state: parsed, loadFailed: false };
    }
    return { state: blankState(), loadFailed: false };
  } catch (e) {
    console.warn("[chat-store] load failed; using in-memory only:", e);
    return { state: blankState(), loadFailed: true };
  }
}

interface ChatStoreState {
  chats: Chat[];
  activeId: string;
  streaming: StreamingState | null;
  loadFailed: boolean;
  storageFull: boolean;
}

let activeConn: ChatWsConnection | null = null;

export const useChatStore = defineStore("chat", {
  state: (): ChatStoreState => ({
    chats: [],
    activeId: "",
    streaming: null,
    loadFailed: false,
    storageFull: false,
  }),

  getters: {
    active(state): Chat {
      return (
        state.chats.find((c) => c.id === state.activeId) ?? state.chats[0]
      );
    },
    sortedChats(state): Chat[] {
      return [...state.chats].sort((a, b) => b.updatedAt - a.updatedAt);
    },
    /** 当前激活会话是否正在流式回答。 */
    isActiveStreaming(state): boolean {
      return state.streaming !== null && state.streaming.chatId === state.activeId;
    },
    sending(): boolean {
      return this.streaming !== null;
    },
  },

  actions: {
    load() {
      const { state, loadFailed } = loadPersisted();
      this.chats = state.chats;
      this.activeId = state.activeId;
      this.loadFailed = loadFailed;
    },

    persist() {
      try {
        const payload: PersistedState = {
          version: STATE_VERSION,
          activeId: this.activeId,
          chats: this.chats,
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      } catch (e) {
        console.warn("[chat-store] save failed:", e);
        this.storageFull = true;
      }
    },

    _chat(id: string): Chat | undefined {
      return this.chats.find((c) => c.id === id);
    },

    create() {
      const c = blankChat();
      this.chats.push(c);
      this.activeId = c.id;
      this.persist();
    },

    switchTo(id: string) {
      if (!this._chat(id)) return;
      this.activeId = id;
      this.persist();
    },

    rename(id: string, newTitle: string) {
      const t = String(newTitle || "").trim();
      if (!t) return;
      const c = this._chat(id);
      if (!c) return;
      c.title = t;
      c.updatedAt = Date.now();
      this.persist();
    },

    remove(id: string) {
      // 若删除的会话正在流式，终止连接。
      if (this.streaming?.chatId === id) this.stop();
      this.chats = this.chats.filter((c) => c.id !== id);
      if (this.chats.length === 0) this.chats.push(blankChat());
      if (id === this.activeId) this.activeId = this.chats[0].id;
      this.persist();
    },

    clearAll() {
      this.stop();
      const c = blankChat();
      this.chats = [c];
      this.activeId = c.id;
      this.persist();
    },

    /** 发送一条用户消息并接收流式回答。流式状态归属 chatId，切换会话不丢。 */
    send(text: string) {
      const t = String(text || "").trim();
      if (!t || t.length > MAX_MESSAGE_CHARS) return;
      const chat = this.active;
      if (!chat) return;
      const targetChatId = chat.id;

      // 新发送取代仍在进行的上一轮（无论归属哪个会话）。
      if (this.streaming) this._failStreaming("（已取消）");

      const userMsg: ChatMessage = { role: "user", content: t, ts: Date.now() };
      chat.messages.push(userMsg);
      chat.updatedAt = Date.now();
      if (chat.title === "新会话") chat.title = autoTitle(t);
      this.persist();

      const history = chat.messages.map((m) => ({
        role: m.role,
        content: m.content || "",
      }));

      this.streaming = { chatId: targetChatId, buffer: "", citations: [], status: "streaming" };

      activeConn = connectChatWs(targetChatId, history, {
        onToken: (chunk) => {
          if (this.streaming?.chatId !== targetChatId) return;
          this.streaming.buffer += chunk;
        },
        onCitation: (cites: Citation[]) => {
          if (this.streaming?.chatId !== targetChatId) return;
          this.streaming.citations = cites;
        },
        onDone: () => {
          if (this.streaming?.chatId !== targetChatId) return;
          const { buffer, citations } = this.streaming;
          this.streaming = null;
          activeConn = null;
          const c = this._chat(targetChatId);
          if (!c) return;
          c.messages.push({
            role: "assistant",
            content: buffer,
            citations,
            ts: Date.now(),
          });
          c.updatedAt = Date.now();
          this.persist();
        },
        onError: (message) => {
          if (this.streaming?.chatId !== targetChatId) return;
          this._failStreaming(message);
        },
      });
    },

    _failStreaming(message: string) {
      if (this.streaming) this.streaming = { ...this.streaming, status: "error", error: message };
      if (activeConn) {
        activeConn.abort();
        activeConn = null;
      }
      // 错误气泡不写入历史，用户可直接重试；短暂展示后清掉。
      setTimeout(() => {
        if (this.streaming?.status === "error") this.streaming = null;
      }, 4000);
    },

    /** 停止当前流式：关闭 WS；已缓冲内容按 done 落盘。 */
    stop() {
      if (activeConn) {
        activeConn.abort();
        activeConn = null;
      }
      if (!this.streaming) return;
      const { chatId, buffer, citations } = this.streaming;
      this.streaming = null;
      const c = this._chat(chatId);
      if (c && buffer) {
        c.messages.push({ role: "assistant", content: buffer, citations, ts: Date.now() });
        c.updatedAt = Date.now();
        this.persist();
      }
    },
  },
});
