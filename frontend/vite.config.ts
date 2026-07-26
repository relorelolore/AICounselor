import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// 后端 CSRF 校验要求 mutating 请求的 Origin 匹配允许源；dev server 代理时
// 统一改写 Origin，浏览器直接访问 vite 端口也能正常调用 /api/admin/*。
const BACKEND = "http://localhost:8000";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
        headers: { Origin: BACKEND },
      },
      "/ws": {
        target: BACKEND,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../web/dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    environmentOptions: {
      jsdom: { url: "http://localhost:5173/" },
    },
  },
});
