<script setup lang="ts">
// ============================================================================
// 管理后台布局：侧边导航（可折叠）+ 顶栏 + <router-view/> 内容区。
// 移动端（<768px）侧栏自动折叠为 64px 图标列。
// ============================================================================

import {
  NButton,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  type MenuOption,
} from "naive-ui";
import { computed, h, onMounted, onUnmounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { useAdminStore } from "../../stores/admin";
import { useThemeStore } from "../../stores/theme";

const adminStore = useAdminStore();
const theme = useThemeStore();
const route = useRoute();
const router = useRouter();

// ---------- 侧栏折叠：窄屏默认收起为图标列 ----------
const collapsed = ref(false);
const mediaQuery = window.matchMedia("(max-width: 768px)");

function onMediaChange(e: MediaQueryListEvent) {
  collapsed.value = e.matches;
}

onMounted(() => {
  collapsed.value = mediaQuery.matches;
  mediaQuery.addEventListener?.("change", onMediaChange);
});
onUnmounted(() => mediaQuery.removeEventListener?.("change", onMediaChange));

// ---------- 菜单 ----------
function renderIcon(text: string) {
  return () => h("span", { class: "menu-icon", "aria-hidden": "true" }, text);
}

const menuOptions: MenuOption[] = [
  {
    label: () => h(RouterLink, { to: "/admin" }, { default: () => "仪表盘" }),
    key: "/admin",
    icon: renderIcon("📊"),
  },
  {
    label: () => h(RouterLink, { to: "/admin/accounts" }, { default: () => "账号" }),
    key: "/admin/accounts",
    icon: renderIcon("👤"),
  },
  {
    label: () => h(RouterLink, { to: "/admin/settings" }, { default: () => "设置" }),
    key: "/admin/settings",
    icon: renderIcon("⚙️"),
  },
];

const activeKey = computed(() => route.path);

// 点击菜单项非链接区域也能跳转（RouterLink 只覆盖文字区域）。
function onMenuSelect(key: string) {
  if (key !== route.path) void router.push(key);
}

const pageTitle = computed(() => {
  switch (route.name) {
    case "admin-accounts":
      return "账号管理";
    case "admin-settings":
      return "系统设置";
    default:
      return "仪表盘";
  }
});

async function onLogout() {
  await adminStore.logout();
  await router.push("/admin/login");
}
</script>

<template>
  <n-layout class="admin-layout" has-sider>
    <n-layout-sider
      class="admin-sider"
      bordered
      collapse-mode="width"
      :width="220"
      :collapsed-width="64"
      :collapsed="collapsed"
    >
      <div class="sider-inner">
        <div class="brand" :class="{ collapsed }">
          <span class="brand-logo">🎓</span>
          <span v-if="!collapsed" class="brand-name">管理后台</span>
        </div>

        <n-menu
          :options="menuOptions"
          :value="activeKey"
          :collapsed="collapsed"
          :collapsed-width="64"
          :collapsed-icon-size="20"
          @update:value="onMenuSelect"
        />

        <div class="sider-footer" :class="{ collapsed }">
          <div v-if="!collapsed" class="user-name" :title="adminStore.me?.username ?? ''">
            👤 {{ adminStore.me?.username }}
          </div>
          <n-button
            quaternary
            size="small"
            :block="!collapsed"
            :title="collapsed ? '退出登录' : undefined"
            @click="onLogout"
          >
            {{ collapsed ? "⏻" : "退出登录" }}
          </n-button>
        </div>
      </div>
    </n-layout-sider>

    <n-layout>
      <n-layout-header class="topbar" bordered>
        <button
          class="icon-btn"
          type="button"
          aria-label="切换侧边栏"
          title="切换侧边栏"
          @click="collapsed = !collapsed"
        >
          ≡
        </button>
        <h1 class="page-title">{{ pageTitle }}</h1>
        <div class="spacer" />
        <button
          class="icon-btn"
          type="button"
          :aria-label="theme.dark ? '切换到浅色' : '切换到深色'"
          :title="theme.dark ? '切换到浅色' : '切换到深色'"
          @click="theme.toggle()"
        >
          {{ theme.dark ? "☀️" : "🌙" }}
        </button>
        <n-button quaternary size="small" @click="onLogout">退出</n-button>
      </n-layout-header>

      <n-layout-content class="content">
        <div class="content-inner">
          <router-view />
        </div>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.admin-layout {
  height: 100vh;
}

.admin-sider {
  background: var(--bg-elev);
}

.sider-inner {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
}

.brand.collapsed {
  justify-content: center;
  padding: 18px 0 14px;
}

.brand-logo {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
  background: var(--brand-grad);
  display: grid;
  place-items: center;
  font-size: 18px;
  box-shadow: 0 4px 12px var(--brand-glow);
}

.brand-name {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
  background: var(--brand-grad);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.menu-icon {
  font-size: 16px;
  line-height: 1;
}

:deep(.n-menu-item-content a) {
  color: inherit;
  text-decoration: none;
}

/* 菜单项圆角 + 内缩，选中态更精致 */
:deep(.n-menu .n-menu-item-content) {
  border-radius: 10px;
  margin: 2px 8px;
  transition: background 0.15s ease;
}

:deep(.n-menu .n-menu-item-content::before) {
  left: 8px;
  right: 8px;
  border-radius: 10px;
}

.sider-footer {
  margin-top: auto;
  padding: 12px 14px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sider-footer.collapsed {
  align-items: center;
  padding: 12px 8px;
}

.user-name {
  font-size: 13px;
  color: var(--fg-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.topbar {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  background: color-mix(in srgb, var(--bg-elev) 82%, transparent);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.page-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}

.spacer {
  flex: 1;
}

.icon-btn {
  border: none;
  background: transparent;
  color: var(--fg-muted);
  font-size: 17px;
  width: 34px;
  height: 34px;
  border-radius: 9px;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.icon-btn:hover {
  background: var(--bg-hover);
  color: var(--fg);
}

.content {
  background: var(--bg);
  /* n-layout-content 默认不撑满剩余高度，强制至少覆盖顶栏以下的视口 */
  min-height: calc(100vh - 56px);
}

.content-inner {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 20px 48px;
  animation: fade-up 0.3s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@media (prefers-reduced-motion: reduce) {
  .content-inner {
    animation: none;
  }
}
</style>
