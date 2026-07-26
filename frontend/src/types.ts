// ============================================================================
// 类型定义 —— 与后端 WS 协议 / admin REST API / localStorage 持久化结构对应
// ============================================================================

/** 单条聊天消息（localStorage 持久化结构，沿用 v1 schema）。 */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  ts: number;
}

export interface Citation {
  filename: string;
  page: number;
  snippet: string;
}

export interface Chat {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

/** localStorage["counselor:state"] 的持久化结构（version 1，与旧前端兼容）。 */
export interface PersistedState {
  version: 1;
  activeId: string;
  chats: Chat[];
}

/** 正在流式回答的临时状态（按 chatId 归属，切换会话不丢）。 */
export interface StreamingState {
  chatId: string;
  buffer: string;
  citations: Citation[];
  status: "streaming" | "error";
  error?: string;
}

// ---------- WS 协议 ----------

export interface WsHistoryItem {
  role: "user" | "assistant";
  content: string;
}

export type WsServerEvent =
  | { event: "token"; data: string }
  | { event: "citation"; data: Citation[] }
  | { event: "done"; data: { finish_reason: string } }
  | { event: "error"; data: string };

// ---------- Admin REST ----------

export interface AdminMe {
  username: string;
  created_at: number;
  last_login_at: number | null;
}

export interface AdminAccount {
  id: string;
  username: string;
  created_at: number;
  updated_at: number;
  last_login_at: number | null;
  failed_attempts: number;
  locked: boolean;
}

export interface AdminSettings {
  llm: {
    base_url: string;
    model_name: string;
    api_key: string;
    temperature: number;
    max_tokens: number;
    timeout: number;
    top_p: number;
    frequency_penalty: number;
    presence_penalty: number;
  };
  retrieval: { k: number; chunk_size: number; chunk_overlap: number };
  paths: { documents_dir: string; data_dir: string; chroma_collection: string };
  embedding: { model: string };
}

export interface ReindexResult {
  added: number;
  skipped: number;
  failed: unknown[];
  items?: { path: string; status: string; chunks?: number; reason?: string; error?: string }[];
  meta_written?: boolean;
}

export interface ReindexLast {
  ts: number;
  force: boolean;
  added: number;
  skipped: number;
  failed: unknown[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  llm: boolean;
  chroma_count: number;
}
