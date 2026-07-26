<script setup lang="ts">
// ============================================================================
// 输入区：自适应高度 textarea + 字数统计 + 发送/停止
// ============================================================================

import { computed, nextTick, onBeforeUnmount, ref } from "vue";

import { useChatStore } from "../../stores/chat";
import { MAX_MESSAGE_CHARS } from "../../utils/format";

const store = useChatStore();

const text = ref("");
const textarea = ref<HTMLTextAreaElement | null>(null);

// 移动端不显示「Enter 发送 / Shift+Enter 换行」提示（软键盘上无此操作）
const mobileMedia = window.matchMedia("(max-width: 768px)");
const isMobile = ref(mobileMedia.matches);
const onMediaChange = (e: MediaQueryListEvent) => {
  isMobile.value = e.matches;
};
mobileMedia.addEventListener?.("change", onMediaChange);
onBeforeUnmount(() => mobileMedia.removeEventListener?.("change", onMediaChange));

const placeholder = computed(() =>
  isMobile.value
    ? "请输入你的问题…"
    : "请输入你的问题…（Enter 发送，Shift+Enter 换行）",
);

const sending = computed(() => store.sending);
const canSend = computed(() => text.value.trim().length > 0 && !sending.value);
const overLimit = computed(() => text.value.length > MAX_MESSAGE_CHARS);

function autoSize() {
  const el = textarea.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

function submit() {
  if (!canSend.value || overLimit.value) return;
  const v = text.value;
  text.value = "";
  void nextTick(autoSize);
  store.send(v);
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submit();
  }
}

/** 空状态点建议卡片后聚焦输入框。 */
function focus() {
  textarea.value?.focus();
}
defineExpose({ focus });
</script>

<template>
  <footer class="composer">
    <div class="composer-box" :class="{ over: overLimit }">
      <textarea
        ref="textarea"
        v-model="text"
        rows="1"
        :placeholder="placeholder"
        aria-label="输入问题"
        @input="autoSize"
        @keydown="onKeydown"
      />
      <div class="composer-actions">
        <span class="char-count" :class="{ over: overLimit }">
          {{ text.length }}/{{ MAX_MESSAGE_CHARS }}
        </span>
        <button
          v-if="!sending"
          class="send-btn"
          type="button"
          :disabled="!canSend || overLimit"
          aria-label="发送"
          @click="submit"
        >
          发送
        </button>
        <button
          v-else
          class="stop-btn"
          type="button"
          aria-label="停止"
          @click="store.stop()"
        >
          ■ 停止
        </button>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.composer {
  padding: 10px 24px 18px;
}

.composer-box {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: var(--shadow-soft);
  transition: border-color 0.15s ease;
}

.composer-box:focus-within {
  border-color: var(--brand-from);
}

.composer-box.over {
  border-color: var(--danger);
}

textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 14.5px;
  line-height: 1.6;
  max-height: 160px;
  padding: 4px 2px;
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.char-count {
  font-size: 12px;
  color: var(--fg-muted);
}

.char-count.over {
  color: var(--danger);
  font-weight: 600;
}

.send-btn,
.stop-btn {
  border: none;
  border-radius: 10px;
  padding: 8px 18px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.send-btn {
  background: var(--brand-grad);
  color: #fff;
  box-shadow: 0 3px 10px rgba(79, 110, 247, 0.35);
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

.send-btn:not(:disabled):hover {
  filter: brightness(1.08);
}

.stop-btn {
  background: var(--bg-hover);
  color: var(--danger);
  border: 1px solid var(--border);
}

.stop-btn:hover {
  border-color: var(--danger);
}
</style>
