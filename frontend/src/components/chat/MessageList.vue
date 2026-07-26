<script setup lang="ts">
// ============================================================================
// 消息列表：历史消息 + 当前会话的流式气泡；智能自动滚动（贴底才跟随）。
// ============================================================================

import { storeToRefs } from "pinia";
import { computed, nextTick, onMounted, ref, watch } from "vue";

import { useChatStore } from "../../stores/chat";
import type { Citation } from "../../types";
import MessageItem from "./MessageItem.vue";

const emit = defineEmits<{
  citation: [cite: Citation];
}>();

const store = useChatStore();
const { streaming } = storeToRefs(store);

const chat = computed(() => store.active);
const showLive = computed(
  () => streaming.value !== null && streaming.value.chatId === chat.value?.id,
);

const scrollEl = ref<HTMLElement | null>(null);

function nearBottom(): boolean {
  const el = scrollEl.value;
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 200;
}

async function scrollToBottom(force = false) {
  await nextTick();
  const el = scrollEl.value;
  if (!el) return;
  if (force || nearBottom()) el.scrollTop = el.scrollHeight;
}

watch(
  () => chat.value?.id,
  () => scrollToBottom(true),
);
watch(
  () => [chat.value?.messages.length, streaming.value?.buffer],
  () => scrollToBottom(),
);

onMounted(() => scrollToBottom(true));
</script>

<template>
  <section ref="scrollEl" class="messages" aria-live="polite">
    <div class="messages-inner">
      <MessageItem
        v-for="(m, idx) in chat?.messages ?? []"
        :key="idx"
        :role="m.role"
        :content="m.content"
        :citations="m.citations"
        @citation="(c: Citation) => emit('citation', c)"
      />
      <MessageItem
        v-if="showLive && streaming"
        role="assistant"
        :content="streaming.buffer"
        :citations="streaming.citations"
        :streaming="streaming.status === 'streaming'"
        :error="streaming.status === 'error' ? streaming.error : undefined"
        @citation="(c: Citation) => emit('citation', c)"
      />
    </div>
  </section>
</template>

<style scoped>
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px 8px;
}

.messages-inner {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
