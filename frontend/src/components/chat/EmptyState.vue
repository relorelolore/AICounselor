<script setup lang="ts">
// ============================================================================
// 空状态：品牌区 + 示例问题卡片（点击即发送）
// ============================================================================

const emit = defineEmits<{
  ask: [text: string];
}>();

const SUGGESTIONS = [
  { icon: "📚", title: "培养方案", text: "我们专业的培养方案有哪些必修环节？" },
  { icon: "🗓️", title: "学业规划", text: "大一到大四应该如何规划课程与竞赛？" },
  { icon: "❓", title: "政策咨询", text: "转专业需要满足哪些条件？" },
];
</script>

<template>
  <section class="empty-state">
    <div class="empty-inner">
      <div class="empty-logo pop-in">🎓</div>
      <h1 class="empty-title">AI 辅导员</h1>
      <p class="empty-sub">基于学校文档的本地 RAG 学业助手，随时解答你的疑问</p>
      <div class="suggestions">
        <button
          v-for="(s, i) in SUGGESTIONS"
          :key="s.title"
          class="suggestion-card fade-up"
          :style="{ animationDelay: `${0.08 + i * 0.07}s` }"
          type="button"
          @click="emit('ask', s.text)"
        >
          <span class="s-icon">{{ s.icon }}</span>
          <span class="s-title">{{ s.title }}</span>
          <span class="s-text">{{ s.text }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.empty-state {
  flex: 1;
  display: grid;
  place-items: center;
  padding: 24px;
  overflow-y: auto;
  background: var(--bg-deco);
}

.empty-inner {
  max-width: 640px;
  text-align: center;
}

.empty-logo {
  width: 72px;
  height: 72px;
  margin: 0 auto 14px;
  display: grid;
  place-items: center;
  font-size: 36px;
  border-radius: 22px;
  background: var(--brand-grad);
  box-shadow:
    0 12px 30px var(--brand-glow),
    inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.empty-title {
  margin: 0 0 6px;
  font-size: 28px;
  letter-spacing: 0.02em;
  background: var(--brand-grad);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.empty-sub {
  margin: 0 0 28px;
  color: var(--fg-muted);
  font-size: 14px;
}

.suggestions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

@media (max-width: 640px) {
  .suggestions {
    grid-template-columns: 1fr;
  }
}

.suggestion-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--bg-elev);
  box-shadow: var(--shadow-soft);
  cursor: pointer;
  text-align: left;
  transition: all 0.18s ease;
}

.suggestion-card:hover {
  transform: translateY(-3px);
  border-color: color-mix(in srgb, var(--brand-from) 55%, transparent);
  box-shadow:
    0 8px 22px rgba(79, 110, 247, 0.14),
    var(--shadow-soft);
}

.s-icon {
  font-size: 20px;
}

.s-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
}

.s-text {
  font-size: 12.5px;
  color: var(--fg-muted);
  line-height: 1.5;
}
</style>
