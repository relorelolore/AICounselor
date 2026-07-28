<script setup lang="ts">
// ============================================================================
// 单条消息气泡：用户（右，渐变）/ 助手（左，卡片，Markdown + 引用 chips）
// 也用于流式气泡（传 streaming 时显示打字光标）。
// ============================================================================

import { computed } from "vue";

import type { Citation } from "../../types";
import { renderMarkdown } from "../../utils/markdown";

const props = defineProps<{
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  citation: [cite: Citation];
}>();

const isAssistant = computed(() => props.role === "assistant");

// 流式期间显示纯文本（与旧前端一致），完成后由外层换用 markdown 渲染的历史消息。
const html = computed(() =>
  isAssistant.value && !props.streaming ? renderMarkdown(props.content) : "",
);
</script>

<template>
  <article class="msg-row" :class="[role, { streaming }]">
    <div v-if="isAssistant" class="avatar" aria-hidden="true">🎓</div>

    <div class="bubble-wrap">
      <div class="bubble" :class="{ error: !!error }">
        <template v-if="isAssistant">
          <div v-if="error" class="error-text">（出错了）{{ error }}</div>
          <div v-else-if="streaming" class="md-body">
            <span class="stream-text">{{ content }}</span><span class="cursor" />
          </div>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-else class="md-body" v-html="html" />
        </template>
        <template v-else>
          <span class="user-text">{{ content }}</span>
        </template>
      </div>

      <div v-if="isAssistant && citations && citations.length" class="cite-chips">
        <button
          v-for="(c, i) in citations"
          :key="i"
          class="cite-chip"
          type="button"
          :title="`《${c.filename}》 第 ${c.page} 页`"
          @click="emit('citation', c)"
        >
          📄 引 {{ i + 1 }}
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.msg-row {
  display: flex;
  gap: 10px;
  padding: 6px 0;
  animation: fade-up 0.3s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@media (prefers-reduced-motion: reduce) {
  .msg-row {
    animation: none;
  }
}

.msg-row.user {
  justify-content: flex-end;
}

.avatar {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  font-size: 17px;
  border-radius: 10px;
  background: var(--brand-grad);
  box-shadow: 0 3px 10px var(--brand-glow);
}

.bubble-wrap {
  max-width: min(78%, 760px);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg-row.user .bubble-wrap {
  align-items: flex-end;
}

.bubble {
  padding: 11px 15px;
  border-radius: 16px;
  font-size: 14.5px;
  line-height: 1.7;
  word-break: break-word;
  box-shadow: var(--shadow-soft);
}

/* 只有纯文本内容需要 pre-wrap；markdown HTML 自己管理空白，
   否则 marked 输出中标签间的换行符会被渲染成多余空行 */
.user-text {
  white-space: pre-wrap;
}

.md-body {
  white-space: normal;
}

.msg-row.assistant .bubble {
  background: var(--bubble-ai-bg);
  color: var(--bubble-ai-fg);
  border: 1px solid var(--border);
  border-top-left-radius: 6px;
}

.msg-row.user .bubble {
  background: var(--bubble-user-bg);
  color: var(--bubble-user-fg);
  border-top-right-radius: 6px;
  box-shadow: 0 4px 14px var(--brand-glow);
}

.bubble.error {
  border-color: var(--danger);
}

.error-text {
  color: var(--danger);
}

.stream-text {
  white-space: pre-wrap;
}

.cursor {
  display: inline-block;
  width: 8px;
  height: 1.1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--brand-from);
  border-radius: 2px;
  animation: blink 0.9s steps(2) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.cite-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cite-chip {
  border: 1px solid var(--border);
  background: var(--bg-elev);
  color: var(--fg-muted);
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.cite-chip:hover {
  color: var(--brand-from);
  border-color: var(--brand-from);
  background: var(--bg-hover);
  box-shadow: 0 2px 8px var(--brand-glow);
  transform: translateY(-1px);
}
</style>
