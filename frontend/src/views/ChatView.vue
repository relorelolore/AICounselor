<script setup lang="ts">
// ============================================================================
// 用户前台主视图：侧栏 + 顶栏 + 消息区 + 输入区 + 引用抽屉
// ============================================================================

import { NDropdown, useDialog, useMessage } from "naive-ui";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import ChatSidebar from "../components/chat/ChatSidebar.vue";
import CitationDrawer from "../components/chat/CitationDrawer.vue";
import Composer from "../components/chat/Composer.vue";
import EmptyState from "../components/chat/EmptyState.vue";
import MessageList from "../components/chat/MessageList.vue";
import { useChatStore } from "../stores/chat";
import { useHealthStore } from "../stores/health";
import { useThemeStore } from "../stores/theme";
import type { Citation } from "../types";

const SIDEBAR_COLLAPSED_KEY = "counselor:sidebar-collapsed";

const store = useChatStore();
const health = useHealthStore();
const theme = useThemeStore();
const dialog = useDialog();
const message = useMessage();

// ---------- 侧栏折叠（桌面默认展开 / 移动默认收起，记忆偏好） ----------
const collapsed = ref(false);
const isDesktop = () => window.matchMedia("(min-width: 769px)").matches;
const mobileOpen = ref(false); // 移动端 overlay 开关

const mediaQuery = window.matchMedia("(min-width: 769px)");
function onMediaChange(e: MediaQueryListEvent) {
  if (!e.matches) {
    collapsed.value = true;
    mobileOpen.value = false;
  }
}

onMounted(() => {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
  } catch {
    /* noop */
  }
  collapsed.value = stored === "1" ? true : stored === "0" ? false : !isDesktop();
  mediaQuery.addEventListener?.("change", onMediaChange);
  if (store.loadFailed) message.warning("数据无法从本地加载，仅本次会话可用");
});
onUnmounted(() => mediaQuery.removeEventListener?.("change", onMediaChange));

function persistCollapsed() {
  try {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed.value ? "1" : "0");
  } catch {
    /* noop */
  }
}

function toggleSidebar() {
  if (isDesktop()) {
    collapsed.value = !collapsed.value;
    persistCollapsed();
  } else {
    mobileOpen.value = !mobileOpen.value;
  }
}

// ---------- 会话操作 ----------
function onSwitch(id: string) {
  store.switchTo(id);
  if (!isDesktop()) mobileOpen.value = false;
}

function onNewChat() {
  store.create();
  if (!isDesktop()) mobileOpen.value = false;
}

function confirmRemove(id: string) {
  const c = store.chats.find((x) => x.id === id);
  if (!c) return;
  dialog.warning({
    title: "删除会话？",
    content: `「${c.title}」将被永久删除，无法撤销。`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: () => store.remove(id),
  });
}

const topActions = [
  { label: "重命名", key: "rename" },
  { label: "删除会话", key: "delete" },
  { label: "清空全部会话", key: "clear-all" },
];

function onTopAction(key: string) {
  if (key === "rename") beginTitleEdit();
  else if (key === "delete") confirmRemove(store.active.id);
  else if (key === "clear-all") {
    dialog.warning({
      title: "清空全部会话？",
      content: `所有 ${store.chats.length} 个会话将被永久删除，无法撤销。`,
      positiveText: "全部删除",
      negativeText: "取消",
      onPositiveClick: () => store.clearAll(),
    });
  }
}

// ---------- 顶栏标题行内编辑 ----------
const titleEditing = ref(false);
const titleDraft = ref("");
const titleInput = ref<HTMLInputElement | null>(null);

function beginTitleEdit() {
  titleDraft.value = store.active.title;
  titleEditing.value = true;
  void nextTick(() => {
    titleInput.value?.focus();
    titleInput.value?.select();
  });
}

function commitTitle() {
  if (!titleEditing.value) return;
  titleEditing.value = false;
  store.rename(store.active.id, titleDraft.value);
}

// ---------- 引用抽屉 ----------
const drawerShow = ref(false);
const selectedCitation = ref<Citation | null>(null);

function openCitation(c: Citation) {
  selectedCitation.value = c;
  drawerShow.value = true;
}

// ---------- 空状态建议问题 ----------
const composer = ref<InstanceType<typeof Composer> | null>(null);

function ask(text: string) {
  store.send(text);
  composer.value?.focus();
}

// ---------- 存储满提示 ----------
watch(
  () => store.storageFull,
  (v) => {
    if (v) {
      message.error("存储空间不足，请删除旧会话");
      store.storageFull = false;
    }
  },
);

const hasContent = computed(
  () => (store.active?.messages.length ?? 0) > 0 || store.isActiveStreaming,
);
</script>

<template>
  <div class="chat-view">
    <!-- 桌面侧栏 -->
    <div v-show="!collapsed" class="sidebar-slot desktop-only">
      <ChatSidebar
        @new-chat="onNewChat"
        @switch="onSwitch"
        @rename="(id, t) => store.rename(id, t)"
        @remove="confirmRemove"
      />
    </div>
    <!-- 移动端 overlay 侧栏 -->
    <template v-if="mobileOpen">
      <div class="sidebar-backdrop mobile-only" @click="mobileOpen = false" />
      <div class="sidebar-slot overlay mobile-only">
        <ChatSidebar
          @new-chat="onNewChat"
          @switch="onSwitch"
          @rename="(id, t) => store.rename(id, t)"
          @remove="confirmRemove"
        />
      </div>
    </template>

    <main class="main">
      <header class="topbar">
        <button
          class="icon-btn"
          type="button"
          aria-label="切换侧边栏"
          title="切换侧边栏"
          @click="toggleSidebar"
        >
          ≡
        </button>

        <input
          v-if="titleEditing"
          ref="titleInput"
          v-model="titleDraft"
          class="chat-title-input"
          type="text"
          maxlength="50"
          @keydown.enter.prevent="commitTitle"
          @keydown.esc.prevent="titleEditing = false"
          @blur="commitTitle"
        />
        <h2
          v-else
          class="chat-title"
          title="点击重命名"
          tabindex="0"
          @click="beginTitleEdit"
          @keydown.enter.prevent="beginTitleEdit"
        >
          {{ store.active?.title || "新会话" }}
        </h2>

        <div class="topbar-spacer" />

        <span class="status" :class="health.status">
          <span class="status-dot" />
          <span class="status-text">{{ health.label }}</span>
        </span>

        <button
          class="icon-btn"
          type="button"
          :aria-label="theme.dark ? '切换到浅色' : '切换到深色'"
          :title="theme.dark ? '切换到浅色' : '切换到深色'"
          @click="theme.toggle()"
        >
          {{ theme.dark ? "☀️" : "🌙" }}
        </button>

        <n-dropdown
          trigger="click"
          :options="topActions"
          placement="bottom-end"
          @select="onTopAction"
        >
          <button class="icon-btn" type="button" aria-label="更多" title="更多">⋯</button>
        </n-dropdown>
      </header>

      <MessageList v-if="hasContent" @citation="openCitation" />
      <EmptyState v-else @ask="ask" />

      <Composer ref="composer" />
    </main>

    <CitationDrawer v-model:show="drawerShow" :citation="selectedCitation" />
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.sidebar-slot {
  height: 100%;
  flex-shrink: 0;
}

.sidebar-slot.overlay {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 60;
  box-shadow: var(--shadow-pop);
}

.sidebar-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(15, 17, 25, 0.45);
  backdrop-filter: blur(2px);
}

.mobile-only {
  display: none;
}

@media (max-width: 768px) {
  .desktop-only {
    display: none !important;
  }
  .mobile-only {
    display: block;
  }
}

.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: color-mix(in srgb, var(--bg-elev) 82%, transparent);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
  z-index: 10;
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

.chat-title {
  margin: 0;
  font-size: 15.5px;
  font-weight: 600;
  cursor: text;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  padding: 4px 6px;
  border-radius: 8px;
}

.chat-title:hover {
  background: var(--bg-hover);
}

.chat-title-input {
  font-size: 15.5px;
  font-weight: 600;
  padding: 4px 8px;
  border: 1px solid var(--brand-from);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  outline: none;
  max-width: 320px;
}

.topbar-spacer {
  flex: 1;
}

.status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--fg-muted);
  flex-shrink: 0;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--fg-muted);
}

.status.ok .status-dot {
  background: var(--ok);
  box-shadow: 0 0 6px var(--ok);
}

.status.degraded .status-dot {
  background: var(--warn);
  box-shadow: 0 0 6px var(--warn);
}

.status.offline .status-dot {
  background: var(--danger);
  box-shadow: 0 0 6px var(--danger);
}

@media (max-width: 560px) {
  .status-text {
    display: none;
  }
}
</style>
