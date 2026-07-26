// ============================================================================
// 健康检查 store：/api/health 30s 轮询，驱动顶栏状态点。
// ============================================================================

import { defineStore } from "pinia";

import type { HealthResponse } from "../types";

type HealthStatus = "checking" | "ok" | "degraded" | "offline";

let timer: ReturnType<typeof setInterval> | null = null;

export const useHealthStore = defineStore("health", {
  state: (): { status: HealthStatus; llm: boolean } => ({
    status: "checking",
    llm: false,
  }),

  getters: {
    label(state): string {
      switch (state.status) {
        case "checking":
          return "检测中…";
        case "ok":
          return "在线";
        case "degraded":
          return state.llm ? "索引未建立" : "模型未连接";
        case "offline":
          return "无法连接后端";
      }
    },
  },

  actions: {
    async refresh() {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 3000);
        const r = await fetch("/api/health", { signal: ctrl.signal });
        clearTimeout(t);
        const data = (await r.json()) as HealthResponse;
        this.llm = data.llm;
        this.status = data.status === "ok" ? "ok" : "degraded";
      } catch {
        this.status = "offline";
      }
    },

    start() {
      if (timer) return;
      void this.refresh();
      timer = setInterval(() => void this.refresh(), 30_000);
    },

    stop() {
      if (timer) clearInterval(timer);
      timer = null;
    },
  },
});
