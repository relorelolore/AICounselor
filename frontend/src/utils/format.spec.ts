// ============================================================================
// utils/format 单测：自动标题、相对时间、分组
// ============================================================================

import { describe, expect, it } from "vitest";

import { autoTitle, formatRelativeTime, groupByUpdatedAt, MAX_TITLE_LEN } from "./format";

describe("autoTitle", () => {
  it("空白 → 新会话", () => {
    expect(autoTitle("   ")).toBe("新会话");
  });

  it("压缩空白字符", () => {
    expect(autoTitle("你好\n  世界")).toBe("你好 世界");
  });

  it("超长截断加省略号", () => {
    const t = autoTitle("x".repeat(100));
    expect(t.length).toBe(MAX_TITLE_LEN + 1);
    expect(t.endsWith("…")).toBe(true);
  });
});

describe("formatRelativeTime", () => {
  const now = new Date("2026-07-26T12:00:00").getTime();

  it("刚刚 / 分钟 / 当天时刻 / 昨天 / 月日", () => {
    expect(formatRelativeTime(now - 30_000, now)).toBe("刚刚");
    expect(formatRelativeTime(now - 5 * 60_000, now)).toBe("5 分钟前");
    expect(formatRelativeTime(new Date("2026-07-26T09:30:00").getTime(), now)).toBe("09:30");
    expect(formatRelativeTime(new Date("2026-07-25T23:00:00").getTime(), now)).toBe("昨天");
    expect(formatRelativeTime(new Date("2026-07-20T10:00:00").getTime(), now)).toBe("7/20");
  });
});

describe("groupByUpdatedAt", () => {
  const now = new Date("2026-07-26T12:00:00").getTime();
  const mk = (updatedAt: number) => ({ updatedAt });

  it("今天/昨天/本周/更早分桶且跳过空组", () => {
    const groups = groupByUpdatedAt(
      [
        mk(now - 60_000), // 今天
        mk(now - 86_400_000 - 60_000), // 昨天
        mk(now - 3 * 86_400_000), // 本周
        mk(now - 30 * 86_400_000), // 更早
      ],
      now,
    );
    expect(groups.map((g) => g.label)).toEqual(["今天", "昨天", "本周", "更早"]);
    expect(groups.every((g) => g.items.length === 1)).toBe(true);
  });

  it("空输入 → 空数组", () => {
    expect(groupByUpdatedAt([], now)).toEqual([]);
  });
});
