// ============================================================================
// 管理后台 REST 客户端 —— 对应 /api/admin/*。
// cookie 会话（credentials: "include"）；401 由调用方决定跳登录。
// ============================================================================

const ADMIN_BASE = "/api/admin";

export class AdminApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

export async function adminApi<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const init: RequestInit = {
    method: options.method ?? "GET",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  };
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  const r = await fetch(ADMIN_BASE + path, init);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const data = (await r.json()) as { detail?: string };
      if (data.detail) detail = data.detail;
    } catch {
      /* noop */
    }
    throw new AdminApiError(r.status, detail);
  }
  if (r.status === 204) return null as T;
  return (await r.json()) as T;
}
