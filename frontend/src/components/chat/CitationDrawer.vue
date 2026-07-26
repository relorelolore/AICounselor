<script setup lang="ts">
// ============================================================================
// 引用详情抽屉（右侧滑出）
// ============================================================================

import { NDrawer, NDrawerContent } from "naive-ui";

import type { Citation } from "../../types";

const show = defineModel<boolean>("show", { required: true });

defineProps<{
  citation: Citation | null;
}>();
</script>

<template>
  <n-drawer v-model:show="show" width="min(420px, 92vw)" placement="right" class="cite-drawer">
    <n-drawer-content closable>
      <template #header>参考资料</template>
      <div v-if="citation" class="cite-card">
        <div class="cite-head">
          <span class="cite-file">📄 《{{ citation.filename }}》</span>
          <span class="cite-page">第 {{ citation.page }} 页</span>
        </div>
        <div class="cite-snippet">{{ citation.snippet }}</div>
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.cite-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cite-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.cite-file {
  font-weight: 600;
  font-size: 14px;
}

.cite-page {
  font-size: 12px;
  color: var(--fg-muted);
  background: var(--bg-hover);
  border-radius: 999px;
  padding: 2px 10px;
}

.cite-snippet {
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--fg);
  background: var(--bg-hover);
  border-radius: 10px;
  padding: 12px 14px;
  white-space: pre-wrap;
}
</style>
