// ============================================================================
// 通用小工具：uuid / 相对时间 / 自动标题 / 会话分组
// ============================================================================

export const MAX_TITLE_LEN = 24;
export const MAX_MESSAGE_CHARS = 4000;

export function uuidv4(): string {
  if (typeof crypto !== "undefined") {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    if (typeof crypto.getRandomValues === "function") {
      const b = crypto.getRandomValues(new Uint8Array(16));
      b[6] = (b[6] & 0x0f) | 0x40;
      b[8] = (b[8] & 0x3f) | 0x80;
      const h: string[] = [];
      for (let i = 0; i < 16; i++) h.push(b[i].toString(16).padStart(2, "0"));
      return `${h.slice(0, 4).join("")}-${h.slice(4, 6).join("")}-${h.slice(6, 8).join("")}-${h.slice(8, 10).join("")}-${h.slice(10, 16).join("")}`;
    }
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** 相对时间：刚刚 / N 分钟前 / HH:MM / 昨天 / M/D。 */
export function formatRelativeTime(ts: number, now = Date.now()): string {
  const diff = now - ts;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  const d = new Date(ts);
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const day = new Date(ts);
  day.setHours(0, 0, 0, 0);
  if (day.getTime() === today.getTime())
    return d.toTimeString().slice(0, 5);
  if (day.getTime() === today.getTime() - 86_400_000) return "昨天";
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function autoTitle(text: string): string {
  const t = String(text || "").trim().replace(/\s+/g, " ");
  if (!t) return "新会话";
  return t.length > MAX_TITLE_LEN ? t.slice(0, MAX_TITLE_LEN) + "…" : t;
}

export interface Grouped<T> {
  label: string;
  items: T[];
}

/** 按 updatedAt 分桶：今天 / 昨天 / 本周 / 更早（入参需已按 updatedAt 倒序）。 */
export function groupByUpdatedAt<T extends { updatedAt: number }>(
  sorted: T[],
  now = Date.now(),
): Grouped<T>[] {
  const today0 = new Date(now);
  today0.setHours(0, 0, 0, 0);
  const yesterday0 = today0.getTime() - 86_400_000;
  const week0 = today0.getTime() - 6 * 86_400_000;
  const groups: Grouped<T>[] = [
    { label: "今天", items: [] },
    { label: "昨天", items: [] },
    { label: "本周", items: [] },
    { label: "更早", items: [] },
  ];
  for (const c of sorted) {
    const t = new Date(c.updatedAt);
    t.setHours(0, 0, 0, 0);
    const tt = t.getTime();
    if (tt >= today0.getTime()) groups[0].items.push(c);
    else if (tt >= yesterday0) groups[1].items.push(c);
    else if (tt >= week0) groups[2].items.push(c);
    else groups[3].items.push(c);
  }
  return groups.filter((g) => g.items.length > 0);
}

export function formatDateTime(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleString();
}
