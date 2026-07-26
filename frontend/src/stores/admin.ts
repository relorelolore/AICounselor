// ============================================================================
// 管理后台会话 store：me / login / logout，401 语义由路由守卫消费。
// ============================================================================

import { defineStore } from "pinia";

import { adminApi, AdminApiError } from "../api/admin";
import type { AdminMe } from "../types";

export const useAdminStore = defineStore("admin", {
  state: (): { me: AdminMe | null; checked: boolean } => ({
    me: null,
    checked: false, // 是否已完成首次 /me 探测（路由守卫用）
  }),

  actions: {
    /** 探测当前登录态；不抛异常，401 时 me=null。 */
    async fetchMe(): Promise<AdminMe | null> {
      try {
        this.me = await adminApi<AdminMe>("/me");
      } catch (e) {
        if (e instanceof AdminApiError && e.status === 401) this.me = null;
        else this.me = null;
      } finally {
        this.checked = true;
      }
      return this.me;
    },

    /** 登录；成功返回 null，失败返回用户可读错误信息。 */
    async login(username: string, password: string): Promise<string | null> {
      try {
        await adminApi("/login", { method: "POST", body: { username, password } });
        await this.fetchMe();
        return null;
      } catch (e) {
        if (e instanceof AdminApiError) {
          if (e.status === 423) return "账号已被锁定，请联系其他管理员解锁";
          if (e.status === 401) return "用户名或密码错误";
          return e.detail || "登录失败";
        }
        return "网络错误，请稍后重试";
      }
    },

    async logout() {
      try {
        await adminApi("/logout", { method: "POST" });
      } catch {
        /* 即使失败也清理本地状态 */
      }
      this.me = null;
    },
  },
});
