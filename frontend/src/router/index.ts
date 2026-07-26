// ============================================================================
// 路由：/ 用户聊天前台；/admin/* 管理后台（登录守卫）。
// ============================================================================

import { createRouter, createWebHistory, type RouteLocationNormalized } from "vue-router";

import { useAdminStore } from "../stores/admin";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "chat",
      component: () => import("../views/ChatView.vue"),
      meta: { title: "AI 辅导员" },
    },
    {
      path: "/admin/login",
      name: "admin-login",
      component: () => import("../views/admin/Login.vue"),
      meta: { title: "登录 · 管理后台" },
    },
    {
      path: "/admin",
      component: () => import("../views/admin/AdminLayout.vue"),
      meta: { requiresAdmin: true },
      children: [
        {
          path: "",
          name: "admin-dashboard",
          component: () => import("../views/admin/Dashboard.vue"),
          meta: { requiresAdmin: true, title: "仪表盘 · 管理后台" },
        },
        {
          path: "accounts",
          name: "admin-accounts",
          component: () => import("../views/admin/Accounts.vue"),
          meta: { requiresAdmin: true, title: "账号 · 管理后台" },
        },
        {
          path: "settings",
          name: "admin-settings",
          component: () => import("../views/admin/Settings.vue"),
          meta: { requiresAdmin: true, title: "设置 · 管理后台" },
        },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach(async (to: RouteLocationNormalized) => {
  const admin = useAdminStore();

  if (to.meta.requiresAdmin) {
    if (!admin.checked) await admin.fetchMe();
    if (!admin.me) {
      return { name: "admin-login", query: { redirect: to.fullPath } };
    }
  }

  if (to.name === "admin-login") {
    if (!admin.checked) await admin.fetchMe();
    if (admin.me) return { path: "/admin" };
  }

  return true;
});

router.afterEach((to) => {
  document.title = (to.meta.title as string) || "AI 辅导员";
});

export default router;
