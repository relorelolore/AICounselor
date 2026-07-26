// ============================================================================
// chat store 单测：localStorage 兼容（旧前端数据无缝迁移）、CRUD、WS 发送流
// ============================================================================

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { STORAGE_KEY, useChatStore } from "./chat";

// ---------- 可控 FakeWebSocket ----------

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.onclose?.({});
  }
  // 测试辅助
  open() {
    this.onopen?.({});
  }
  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

vi.stubGlobal("WebSocket", FakeWebSocket);

function freshStore() {
  setActivePinia(createPinia());
  return useChatStore();
}

beforeEach(() => {
  localStorage.clear();
  FakeWebSocket.instances = [];
});

describe("localStorage 兼容", () => {
  it("读取旧前端（v1）持久化数据，会话不丢", () => {
    const legacy = {
      version: 1,
      activeId: "aaa",
      chats: [
        {
          id: "aaa",
          title: "旧会话",
          createdAt: 1700000000000,
          updatedAt: 1700000001000,
          messages: [
            { role: "user", content: "你好", ts: 1700000000500 },
            {
              role: "assistant",
              content: "你好！",
              citations: [{ filename: "手册.pdf", page: 3, snippet: "……" }],
              ts: 1700000000800,
            },
          ],
        },
      ],
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(legacy));

    const store = freshStore();
    store.load();

    expect(store.loadFailed).toBe(false);
    expect(store.activeId).toBe("aaa");
    expect(store.chats).toHaveLength(1);
    expect(store.active.title).toBe("旧会话");
    expect(store.active.messages).toHaveLength(2);
    expect(store.active.messages[1].citations?.[0].filename).toBe("手册.pdf");
  });

  it("损坏数据回退为全新空会话并标记 loadFailed", () => {
    localStorage.setItem(STORAGE_KEY, "{not-json");
    const store = freshStore();
    store.load();
    expect(store.loadFailed).toBe(true);
    expect(store.chats).toHaveLength(1);
    expect(store.chats[0].messages).toHaveLength(0);
  });

  it("版本不符视为无数据", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 99, chats: [] }));
    const store = freshStore();
    store.load();
    expect(store.loadFailed).toBe(false);
    expect(store.chats).toHaveLength(1);
  });

  it("mutate 后写回 localStorage（同一 key）", () => {
    const store = freshStore();
    store.load();
    store.create();
    const raw = localStorage.getItem(STORAGE_KEY);
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    expect(parsed.version).toBe(1);
    expect(parsed.chats).toHaveLength(2);
    expect(parsed.activeId).toBe(store.activeId);
  });
});

describe("会话 CRUD", () => {
  it("create / switchTo / rename / remove / clearAll", () => {
    const store = freshStore();
    store.load();
    const first = store.active.id;

    store.create();
    expect(store.chats).toHaveLength(2);
    const second = store.active.id;
    expect(second).not.toBe(first);

    store.switchTo(first);
    expect(store.activeId).toBe(first);

    store.rename(first, "  新标题  ");
    expect(store.active.title).toBe("新标题");
    store.rename(first, "   ");
    expect(store.active.title).toBe("新标题");

    store.remove(first);
    expect(store.chats).toHaveLength(1);
    expect(store.activeId).toBe(second);

    store.clearAll();
    expect(store.chats).toHaveLength(1);
    expect(store.chats[0].messages).toHaveLength(0);
  });

  it("删除全部会话后自动补一个空会话", () => {
    const store = freshStore();
    store.load();
    store.remove(store.activeId);
    expect(store.chats).toHaveLength(1);
    expect(store.chats[0].title).toBe("新会话");
  });
});

describe("WS 发送流", () => {
  function openAndDrain() {
    const ws = FakeWebSocket.instances[0];
    ws.open();
    return ws;
  }

  it("发送：用户消息入列 + 自动标题 + 首帧带完整历史", () => {
    const store = freshStore();
    store.load();
    store.send("  培养方案有哪些必修环节？  ");

    expect(store.active.messages).toHaveLength(1);
    expect(store.active.messages[0].role).toBe("user");
    expect(store.active.messages[0].content).toBe("培养方案有哪些必修环节？");
    expect(store.active.title).toBe("培养方案有哪些必修环节？");
    expect(store.sending).toBe(true);

    const ws = openAndDrain();
    expect(ws.url).toContain("/ws/chat");
    const frame = JSON.parse(ws.sent[0]);
    expect(frame.session_id).toBe(store.active.id);
    expect(frame.history).toEqual([
      { role: "user", content: "培养方案有哪些必修环节？" },
    ]);
  });

  it("token/citation/done 事件驱动流式气泡并落盘", () => {
    const store = freshStore();
    store.load();
    const chatId = store.active.id;
    store.send("问题");
    const ws = openAndDrain();

    ws.emit({ event: "token", data: "回答内容" });
    expect(store.streaming?.buffer).toBe("回答内容");

    const cites = [{ filename: "方案.pdf", page: 1, snippet: "片段" }];
    ws.emit({ event: "citation", data: cites });
    expect(store.streaming?.citations).toEqual(cites);

    ws.emit({ event: "done", data: { finish_reason: "stop" } });
    expect(store.streaming).toBeNull();
    const chat = store.chats.find((c) => c.id === chatId)!;
    expect(chat.messages).toHaveLength(2);
    expect(chat.messages[1]).toMatchObject({
      role: "assistant",
      content: "回答内容",
      citations: cites,
    });

    // 已持久化
    const persisted = JSON.parse(localStorage.getItem(STORAGE_KEY)!);
    expect(persisted.chats[0].messages).toHaveLength(2);
  });

  it("error 事件：不写入助手消息，可重试", () => {
    const store = freshStore();
    store.load();
    store.send("问题");
    const ws = openAndDrain();
    ws.emit({ event: "error", data: "agent error" });
    expect(store.streaming?.status).toBe("error");
    expect(store.active.messages).toHaveLength(1);
  });

  it("stop：已缓冲内容按 done 落盘", () => {
    const store = freshStore();
    store.load();
    store.send("问题");
    const ws = openAndDrain();
    ws.emit({ event: "token", data: "半截回答" });
    store.stop();
    expect(store.streaming).toBeNull();
    expect(store.active.messages).toHaveLength(2);
    expect(store.active.messages[1].content).toBe("半截回答");
  });

  it("流式归属 chatId：切换会话不影响接收，切回可见", () => {
    const store = freshStore();
    store.load();
    const chatId = store.active.id;
    store.send("问题");
    const ws = openAndDrain();

    store.create(); // 切到新会话
    expect(store.activeId).not.toBe(chatId);
    expect(store.isActiveStreaming).toBe(false);

    ws.emit({ event: "token", data: "回答" });
    ws.emit({ event: "done", data: { finish_reason: "stop" } });

    const target = store.chats.find((c) => c.id === chatId)!;
    expect(target.messages).toHaveLength(2);
    expect(target.messages[1].content).toBe("回答");
    // 回答写入的是原会话，不是当前会话
    expect(store.active.messages).toHaveLength(0);
  });

  it("超长消息（>4000）直接忽略", () => {
    const store = freshStore();
    store.load();
    store.send("x".repeat(4001));
    expect(store.active.messages).toHaveLength(0);
    expect(FakeWebSocket.instances).toHaveLength(0);
  });
});
