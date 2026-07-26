<script setup lang="ts">
// ============================================================================
// 仪表盘：欢迎语 + 当前配置摘要 + 重建索引 + 最近索引。
// settings 与 reindex/last 并行加载，失败静默（卡片内显示「加载失败」）。
// ============================================================================

import {
  NButton,
  NCard,
  NCheckbox,
  NDataTable,
  NTag,
  useDialog,
  useMessage,
  type DataTableColumns,
} from "naive-ui";
import { h, onMounted, ref } from "vue";

import { adminApi, AdminApiError } from "../../api/admin";
import { useAdminStore } from "../../stores/admin";
import type { AdminSettings, ReindexLast, ReindexResult } from "../../types";
import { formatDateTime } from "../../utils/format";

const adminStore = useAdminStore();
const dialog = useDialog();
const message = useMessage();

type LoadState = "loading" | "ok" | "error";

// ---------- 配置摘要 ----------
const settings = ref<AdminSettings | null>(null);
const settingsState = ref<LoadState>("loading");

async function loadSettings() {
  settingsState.value = "loading";
  try {
    settings.value = await adminApi<AdminSettings>("/settings");
    settingsState.value = "ok";
  } catch {
    settingsState.value = "error";
  }
}

// ---------- 最近索引 ----------
const last = ref<ReindexLast | null>(null);
const lastState = ref<LoadState>("loading");

async function loadLast() {
  try {
    const r = await adminApi<{ last: ReindexLast | null }>("/reindex/last");
    last.value = r.last;
    lastState.value = "ok";
  } catch {
    lastState.value = "error";
  }
}

onMounted(() => {
  void loadSettings();
  void loadLast();
});

// ---------- 重建索引 ----------
const force = ref(false);
const running = ref(false);
const result = ref<ReindexResult | null>(null);

interface ReindexItem {
  path: string;
  status: string;
  chunks?: number;
  reason?: string;
  error?: string;
}

const STATUS_META: Record<string, { text: string; type: "success" | "warning" | "error" }> = {
  added: { text: "新增", type: "success" },
  skipped: { text: "跳过", type: "warning" },
  failed: { text: "失败", type: "error" },
};

const itemColumns: DataTableColumns<ReindexItem> = [
  { title: "文件", key: "path", ellipsis: { tooltip: true } },
  {
    title: "状态",
    key: "status",
    width: 90,
    render(row) {
      const meta = STATUS_META[row.status] ?? { text: row.status, type: "warning" as const };
      return h(NTag, { size: "small", type: meta.type, bordered: false }, { default: () => meta.text });
    },
  },
  {
    title: "详情",
    key: "detail",
    render(row) {
      if (row.chunks != null) return `${row.chunks} chunks`;
      return row.reason || row.error || "—";
    },
  },
];

function onReindexClick() {
  dialog.warning({
    title: "确认重建索引",
    content: "将扫描文档目录，可能耗时较长。是否继续？",
    positiveText: "确认",
    negativeText: "取消",
    onPositiveClick: () => {
      void runReindex();
    },
  });
}

async function runReindex() {
  running.value = true;
  result.value = null;
  try {
    result.value = await adminApi<ReindexResult>("/reindex", {
      method: "POST",
      body: { force: force.value },
    });
    message.success("索引重建完成");
    void loadLast();
  } catch (e) {
    if (e instanceof AdminApiError && e.status === 409) {
      message.warning("已有重建任务进行中");
    } else if (e instanceof AdminApiError) {
      message.error(e.detail || e.message);
    } else {
      message.error("网络错误，请稍后重试");
    }
  } finally {
    running.value = false;
  }
}
</script>

<template>
  <div class="dashboard">
    <h1 class="greeting">欢迎，{{ adminStore.me?.username }}</h1>

    <n-card class="card" title="当前配置摘要" :bordered="false">
      <div v-if="settingsState === 'loading'" class="state-text">加载中…</div>
      <div v-else-if="settingsState === 'error'" class="state-text">加载失败</div>
      <div v-else-if="settings" class="desc-grid">
        <div class="desc-item">
          <span class="desc-label">LLM 模型</span>
          <span class="desc-value">{{ settings.llm.model_name }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">LLM 端点</span>
          <span class="desc-value">{{ settings.llm.base_url }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">Temperature</span>
          <span class="desc-value">{{ settings.llm.temperature }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">Max tokens</span>
          <span class="desc-value">{{ settings.llm.max_tokens }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">检索 k</span>
          <span class="desc-value">{{ settings.retrieval.k }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">Chunk size / overlap</span>
          <span class="desc-value">
            {{ settings.retrieval.chunk_size }} / {{ settings.retrieval.chunk_overlap }}
          </span>
        </div>
        <div class="desc-item">
          <span class="desc-label">Embedding 模型</span>
          <span class="desc-value">{{ settings.embedding.model }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">文档目录</span>
          <span class="desc-value">{{ settings.paths.documents_dir }}</span>
        </div>
      </div>
    </n-card>

    <n-card class="card" title="重建索引" :bordered="false">
      <p class="muted">
        扫描 <code class="doc-path">{{ settings?.paths.documents_dir ?? "./Documents" }}</code>
        目录，构建向量数据库。
      </p>
      <n-checkbox v-model:checked="force" :disabled="running">
        强制重建（忽略文件指纹缓存）
      </n-checkbox>
      <div class="actions-row">
        <n-button type="primary" :loading="running" :disabled="running" @click="onReindexClick">
          {{ running ? "处理中…" : "重建索引" }}
        </n-button>
      </div>

      <div v-if="result" class="result">
        <p class="result-summary">
          <strong>{{ result.added }}</strong> 新增，<strong>{{ result.skipped }}</strong> 跳过，<strong>{{ result.failed.length }}</strong> 失败
        </p>
        <n-data-table
          v-if="result.items && result.items.length"
          :columns="itemColumns"
          :data="result.items"
          size="small"
          :bordered="false"
          :single-line="false"
        />
      </div>
    </n-card>

    <n-card class="card" title="最近索引" :bordered="false">
      <div v-if="lastState === 'loading'" class="state-text">加载中…</div>
      <div v-else-if="lastState === 'error'" class="state-text">加载失败</div>
      <div v-else-if="!last" class="state-text">暂无记录</div>
      <div v-else class="desc-grid">
        <div class="desc-item">
          <span class="desc-label">时间</span>
          <span class="desc-value">{{ formatDateTime(last.ts) }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">模式</span>
          <span class="desc-value">{{ last.force ? "强制重建" : "增量" }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">新增</span>
          <span class="desc-value">{{ last.added }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">跳过</span>
          <span class="desc-value">{{ last.skipped }}</span>
        </div>
        <div class="desc-item">
          <span class="desc-label">失败</span>
          <span class="desc-value">{{ last.failed.length }}</span>
        </div>
      </div>
    </n-card>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.greeting {
  margin: 4px 0 0;
  font-size: 22px;
  font-weight: 700;
}

.card {
  box-shadow: var(--shadow-soft);
}

.state-text {
  color: var(--fg-muted);
  font-size: 13.5px;
}

.muted {
  margin: 0 0 12px;
  color: var(--fg-muted);
  font-size: 13.5px;
}

.doc-path {
  background: rgba(127, 133, 160, 0.16);
  border-radius: 5px;
  padding: 0.1em 0.4em;
  font-size: 0.9em;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

.desc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 10px 24px;
}

.desc-item {
  display: flex;
  gap: 12px;
  font-size: 13.5px;
  line-height: 1.6;
  min-width: 0;
}

.desc-label {
  color: var(--fg-muted);
  flex-shrink: 0;
  min-width: 120px;
}

.desc-value {
  word-break: break-all;
  min-width: 0;
}

.actions-row {
  margin-top: 14px;
}

.result {
  margin-top: 16px;
  border-top: 1px dashed var(--border);
  padding-top: 14px;
}

.result-summary {
  margin: 0 0 12px;
  font-size: 13.5px;
  color: var(--fg-muted);
}

.result-summary strong {
  color: var(--brand-from);
  font-size: 15px;
}
</style>
