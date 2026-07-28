<script setup lang="ts">
// ============================================================================
// 会话侧栏：品牌头 + 新会话 + 分组会话列表（行内重命名 / ⋯ 菜单删除）
// ============================================================================

import { NDropdown } from "naive-ui";
import { computed, nextTick, ref } from "vue";

import { useChatStore } from "../../stores/chat";
import type { Chat } from "../../types";
import { formatRelativeTime, groupByUpdatedAt } from "../../utils/format";

const emit = defineEmits<{
  newChat: [];
  switch: [id: string];
  rename: [id: string, title: string];
  remove: [id: string];
}>();

const store = useChatStore();

const groups = computed(() => groupByUpdatedAt(store.sortedChats));

// ---------- 行内重命名 ----------
const editingId = ref<string | null>(null);
const editingTitle = ref("");
const editInput = ref<HTMLInputElement | null>(null);

function beginRename(chat: Chat) {
  editingId.value = chat.id;
  editingTitle.value = chat.title;
  void nextTick(() => {
    editInput.value?.focus();
    editInput.value?.select();
  });
}

function commitRename() {
  const id = editingId.value;
  if (!id) return;
  editingId.value = null;
  const t = editingTitle.value.trim();
  if (t) emit("rename", id, t);
}

function cancelRename() {
  editingId.value = null;
}

// ---------- ⋯ 菜单 ----------
const menuOptions = [
  { label: "重命名", key: "rename" },
  { label: "删除", key: "delete", props: { style: "color: var(--danger)" } },
];

function onMenuSelect(key: string, chat: Chat) {
  if (key === "rename") beginRename(chat);
  else if (key === "delete") emit("remove", chat.id);
}

function onItemClick(chat: Chat) {
  if (editingId.value === chat.id) return;
  emit("switch", chat.id);
}
</script>

<template>
  <aside class="sidebar" aria-label="会话列表">
    <header class="sidebar-header">
      <div class="brand">
        <span class="brand-logo">🎓</span>
        <span class="brand-name">AI 辅导员</span>
      </div>
    </header>

    <button class="new-chat-btn" type="button" @click="emit('newChat')">
      <span class="plus">＋</span> 新会话
    </button>

    <nav class="chat-list">
      <template v-for="g in groups" :key="g.label">
        <div class="chat-group-title">{{ g.label }}</div>
        <div
          v-for="chat in g.items"
          :key="chat.id"
          class="chat-item"
          :class="{ active: chat.id === store.activeId }"
          @click="onItemClick(chat)"
        >
          <input
            v-if="editingId === chat.id"
            ref="editInput"
            v-model="editingTitle"
            class="chat-rename-input"
            type="text"
            maxlength="50"
            @click.stop
            @keydown.enter.prevent="commitRename"
            @keydown.esc.prevent="cancelRename"
            @blur="commitRename"
          />
          <template v-else>
            <div class="chat-text">
              <span class="chat-title-text" :title="chat.title">{{ chat.title }}</span>
              <span class="chat-time">{{ formatRelativeTime(chat.updatedAt) }}</span>
            </div>
            <n-dropdown
              trigger="click"
              :options="menuOptions"
              placement="bottom-end"
              @select="(key: string) => onMenuSelect(key, chat)"
            >
              <button
                class="chat-menu-btn"
                type="button"
                aria-label="更多"
                title="更多"
                @click.stop
              >
                ⋯
              </button>
            </n-dropdown>
          </template>
        </div>
      </template>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  flex-shrink: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-elev);
  border-right: 1px solid var(--border);
  transition: margin-left 0.25s ease;
}

.sidebar-header {
  padding: 16px 16px 10px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-logo {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  font-size: 18px;
  border-radius: 10px;
  background: var(--brand-grad);
  box-shadow: 0 4px 12px var(--brand-glow);
}

.brand-name {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.02em;
  background: var(--brand-grad);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.new-chat-btn {
  margin: 4px 14px 10px;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--brand-from) 45%, transparent);
  border-radius: 12px;
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--brand-from) 10%, transparent),
    color-mix(in srgb, var(--brand-to) 10%, transparent)
  );
  color: var(--brand-from);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.new-chat-btn:hover {
  border-color: var(--brand-from);
  box-shadow: 0 4px 14px var(--brand-glow);
  transform: translateY(-1px);
}

.new-chat-btn:active {
  transform: translateY(0);
}

.new-chat-btn .plus {
  font-weight: 700;
}

.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}

.chat-group-title {
  padding: 12px 10px 5px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--fg-muted);
}

.chat-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 9px 10px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.chat-item:hover {
  background: var(--bg-hover);
}

.chat-item.active {
  background: var(--bg-active);
}

/* 选中会话左侧的品牌色指示条 */
.chat-item.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 999px;
  background: var(--brand-grad);
}

.chat-item.active .chat-title-text {
  font-weight: 600;
}

.chat-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-title-text {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-time {
  font-size: 11px;
  color: var(--fg-muted);
}

.chat-menu-btn {
  border: none;
  background: transparent;
  color: var(--fg-muted);
  font-size: 15px;
  padding: 2px 6px;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.chat-item:hover .chat-menu-btn,
.chat-item.active .chat-menu-btn {
  opacity: 1;
}

.chat-menu-btn:hover {
  background: var(--bg-active);
  color: var(--fg);
}

.chat-rename-input {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  padding: 4px 8px;
  border: 1px solid var(--brand-from);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  outline: none;
}
</style>
