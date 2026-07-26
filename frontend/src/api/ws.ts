// ============================================================================
// WebSocket 聊天客户端 —— 协议与后端 app/routes_chat.py 严格对应：
//   首帧发送 { session_id, history }；服务端回 token / citation / done / error。
// ============================================================================

import type { Citation, WsHistoryItem, WsServerEvent } from "../types";

export interface ChatWsHandlers {
  onToken(chunk: string): void;
  onCitation(cites: Citation[]): void;
  onDone(): void;
  onError(message: string): void;
}

export interface ChatWsConnection {
  abort(): void;
}

const CONNECT_TIMEOUT_MS = 90_000;

export function connectChatWs(
  sessionId: string,
  history: WsHistoryItem[],
  handlers: ChatWsHandlers,
): ChatWsConnection {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws/chat`);
  let settled = false;

  const timer = setTimeout(() => {
    if (settled) return;
    settled = true;
    try {
      ws.close();
    } catch {
      /* noop */
    }
    handlers.onError("连接超时（90s）");
  }, CONNECT_TIMEOUT_MS);

  const finish = () => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
  };

  ws.onopen = () => {
    try {
      ws.send(JSON.stringify({ session_id: sessionId, history }));
    } catch (e) {
      finish();
      handlers.onError("发送失败：" + e);
      try {
        ws.close();
      } catch {
        /* noop */
      }
    }
  };

  ws.onmessage = (ev) => {
    let payload: WsServerEvent;
    try {
      payload = JSON.parse(ev.data as string);
    } catch {
      return;
    }
    if (payload.event === "token") handlers.onToken(payload.data || "");
    else if (payload.event === "citation") handlers.onCitation(payload.data || []);
    else if (payload.event === "done") {
      finish();
      handlers.onDone();
    } else if (payload.event === "error") {
      finish();
      handlers.onError(payload.data || "未知错误");
    }
  };

  ws.onerror = () => {
    finish();
    handlers.onError("WebSocket 连接失败");
  };
  ws.onclose = () => {
    clearTimeout(timer);
  };

  return {
    abort() {
      finish();
      try {
        ws.close();
      } catch {
        /* noop */
      }
    },
  };
}
