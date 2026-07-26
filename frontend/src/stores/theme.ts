// ============================================================================
// 主题 store：明 / 暗，跟随系统 + 手动切换，localStorage 记忆。
// ============================================================================

import { defineStore } from "pinia";

const THEME_KEY = "counselor:theme";

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches
  );
}

function applyToDocument(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
}

export const useThemeStore = defineStore("theme", {
  state: (): { dark: boolean } => ({ dark: false }),

  actions: {
    init() {
      let stored: string | null = null;
      try {
        stored = localStorage.getItem(THEME_KEY);
      } catch {
        /* noop */
      }
      this.dark = stored === "dark" ? true : stored === "light" ? false : systemPrefersDark();
      applyToDocument(this.dark);
      // 未手动选择时跟随系统变化。
      window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", (e) => {
        let manual: string | null = null;
        try {
          manual = localStorage.getItem(THEME_KEY);
        } catch {
          /* noop */
        }
        if (manual !== "dark" && manual !== "light") {
          this.dark = e.matches;
          applyToDocument(this.dark);
        }
      });
    },

    toggle() {
      this.dark = !this.dark;
      applyToDocument(this.dark);
      try {
        localStorage.setItem(THEME_KEY, this.dark ? "dark" : "light");
      } catch {
        /* noop */
      }
    },
  },
});
