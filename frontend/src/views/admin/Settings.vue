<script setup lang="ts">
// ============================================================================
// 系统设置：5 个分组卡片，每组独立保存（只提交本组字段）。
// restart_required 非空时顶部显示「需重启」banner。
// ============================================================================

import {
  NAlert,
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSpin,
  useMessage,
} from "naive-ui";
import { onMounted, reactive, ref } from "vue";

import { adminApi, AdminApiError } from "../../api/admin";
import type { AdminSettings } from "../../types";

const message = useMessage();

// n-input-number 的 v-model 类型为 number | null，数字字段据此建模。
type Num = number | null;

interface SettingsForm {
  llm: {
    base_url: string;
    model_name: string;
    api_key: string;
    temperature: Num;
    max_tokens: Num;
    timeout: Num;
    top_p: Num;
    frequency_penalty: Num;
    presence_penalty: Num;
  };
  retrieval: { k: Num; chunk_size: Num; chunk_overlap: Num };
  paths: { documents_dir: string; data_dir: string; chroma_collection: string };
  embedding: { model: string };
}

// 响应式副本：不直接改 store / 服务端对象。
const form = reactive<SettingsForm>({
  llm: {
    base_url: "",
    model_name: "",
    api_key: "",
    temperature: null,
    max_tokens: null,
    timeout: null,
    top_p: null,
    frequency_penalty: null,
    presence_penalty: null,
  },
  retrieval: { k: null, chunk_size: null, chunk_overlap: null },
  paths: { documents_dir: "", data_dir: "", chroma_collection: "" },
  embedding: { model: "" },
});

const loading = ref(true);
const restartFields = ref<string[]>([]);

async function load() {
  try {
    const s = await adminApi<AdminSettings>("/settings");
    form.llm = { ...s.llm };
    form.retrieval = { ...s.retrieval };
    form.paths = { ...s.paths };
    form.embedding = { ...s.embedding };
  } catch (e) {
    message.error(e instanceof AdminApiError ? e.detail || e.message : "设置加载失败");
  }
}

onMounted(async () => {
  await load();
  loading.value = false;
});

// ---------- 分组定义 ----------
interface FieldDef {
  key: string;
  numeric?: boolean;
}

type SaveKey = "llm-params" | "llm-conn" | "retrieval" | "paths" | "embedding";

interface GroupDef {
  id: SaveKey;
  section: keyof SettingsForm;
  fields: FieldDef[];
}

const groupLlmParams: GroupDef = {
  id: "llm-params",
  section: "llm",
  fields: [
    { key: "temperature", numeric: true },
    { key: "max_tokens", numeric: true },
    { key: "top_p", numeric: true },
    { key: "frequency_penalty", numeric: true },
    { key: "presence_penalty", numeric: true },
  ],
};

const groupLlmConn: GroupDef = {
  id: "llm-conn",
  section: "llm",
  fields: [{ key: "api_key" }, { key: "base_url" }, { key: "model_name" }, { key: "timeout", numeric: true }],
};

const groupRetrieval: GroupDef = {
  id: "retrieval",
  section: "retrieval",
  fields: [
    { key: "k", numeric: true },
    { key: "chunk_size", numeric: true },
    { key: "chunk_overlap", numeric: true },
  ],
};

const groupPaths: GroupDef = {
  id: "paths",
  section: "paths",
  fields: [{ key: "documents_dir" }, { key: "data_dir" }, { key: "chroma_collection" }],
};

const groupEmbedding: GroupDef = {
  id: "embedding",
  section: "embedding",
  fields: [{ key: "model" }],
};

const saving = reactive<Record<SaveKey, boolean>>({
  "llm-params": false,
  "llm-conn": false,
  retrieval: false,
  paths: false,
  embedding: false,
});

async function saveGroup(group: GroupDef) {
  const src = form[group.section] as unknown as Record<string, string | number | null>;
  const payload: Record<string, string | number> = {};
  for (const f of group.fields) {
    const v = src[f.key];
    if (f.numeric) {
      if (v === null || v === "") {
        message.error("请填写完整的数字字段");
        return;
      }
      payload[f.key] = Number(v);
    } else {
      payload[f.key] = String(v ?? "");
    }
  }
  saving[group.id] = true;
  try {
    const r = await adminApi<{ sections: unknown; restart_required: string[] }>("/settings", {
      method: "PUT",
      body: { sections: { [group.section]: payload } },
    });
    if (r.restart_required && r.restart_required.length) {
      restartFields.value = r.restart_required;
      message.warning("已保存，部分修改需重启服务后生效");
    } else {
      message.success("已保存");
    }
    await load();
  } catch (e) {
    message.error(e instanceof AdminApiError ? e.detail || e.message : "保存失败");
  } finally {
    saving[group.id] = false;
  }
}
</script>

<template>
  <div class="settings-page">
    <h1 class="page-heading">系统设置</h1>

    <n-alert
      v-if="restartFields.length"
      type="warning"
      class="restart-banner"
      :bordered="false"
      closable
      @close="restartFields = []"
    >
      以下修改需重启服务后才能生效：{{ restartFields.join("，") }}
    </n-alert>

    <n-spin :show="loading">
      <div class="groups">
        <!-- LLM 推理参数（热生效） -->
        <n-card class="card" :bordered="false">
          <template #header>
            <div class="card-head">
              <span class="card-title">LLM 推理参数</span>
              <span class="badge hot">热生效</span>
            </div>
          </template>
          <n-form label-placement="left" :label-width="210">
            <n-form-item label="Temperature (0–2)">
              <n-input-number
                v-model:value="form.llm.temperature"
                class="num-input"
                :min="0"
                :max="2"
                :step="0.1"
              />
            </n-form-item>
            <n-form-item label="Max tokens (1–32768)">
              <n-input-number
                v-model:value="form.llm.max_tokens"
                class="num-input"
                :min="1"
                :max="32768"
                :step="1"
              />
            </n-form-item>
            <n-form-item label="Top P (0–1)">
              <n-input-number
                v-model:value="form.llm.top_p"
                class="num-input"
                :min="0"
                :max="1"
                :step="0.05"
              />
            </n-form-item>
            <n-form-item label="Frequency penalty (-2–2)">
              <n-input-number
                v-model:value="form.llm.frequency_penalty"
                class="num-input"
                :min="-2"
                :max="2"
                :step="0.1"
              />
            </n-form-item>
            <n-form-item label="Presence penalty (-2–2)">
              <n-input-number
                v-model:value="form.llm.presence_penalty"
                class="num-input"
                :min="-2"
                :max="2"
                :step="0.1"
              />
            </n-form-item>
          </n-form>
          <div class="card-actions">
            <n-button
              type="primary"
              :loading="saving['llm-params']"
              @click="saveGroup(groupLlmParams)"
            >
              保存 LLM 推理
            </n-button>
          </div>
        </n-card>

        <!-- LLM 连接（需重启） -->
        <n-card class="card" :bordered="false">
          <template #header>
            <div class="card-head">
              <span class="card-title">LLM 连接</span>
              <span class="badge restart">需重启</span>
            </div>
          </template>
          <n-form label-placement="left" :label-width="210">
            <n-form-item label="Base URL">
              <n-input v-model:value="form.llm.base_url" placeholder="https://api.example.com/v1" />
            </n-form-item>
            <n-form-item label="API key">
              <n-input
                v-model:value="form.llm.api_key"
                type="password"
                show-password-on="click"
                placeholder="llama.cpp（本地默认）"
              />
            </n-form-item>
            <n-form-item label="Model name">
              <n-input v-model:value="form.llm.model_name" placeholder="模型名称" />
            </n-form-item>
            <n-form-item label="Timeout (5–600 s)">
              <n-input-number
                v-model:value="form.llm.timeout"
                class="num-input"
                :min="5"
                :max="600"
                :step="1"
              />
            </n-form-item>
          </n-form>
          <div class="card-actions">
            <n-button
              type="primary"
              :loading="saving['llm-conn']"
              @click="saveGroup(groupLlmConn)"
            >
              保存 LLM 连接
            </n-button>
          </div>
        </n-card>

        <!-- 检索（热生效） -->
        <n-card class="card" :bordered="false">
          <template #header>
            <div class="card-head">
              <span class="card-title">检索</span>
              <span class="badge hot">热生效</span>
            </div>
          </template>
          <n-form label-placement="left" :label-width="210">
            <n-form-item label="k (1–50)">
              <n-input-number
                v-model:value="form.retrieval.k"
                class="num-input"
                :min="1"
                :max="50"
                :step="1"
              />
            </n-form-item>
            <n-form-item label="Chunk size (50–5000)">
              <n-input-number
                v-model:value="form.retrieval.chunk_size"
                class="num-input"
                :min="50"
                :max="5000"
                :step="1"
              />
            </n-form-item>
            <n-form-item label="Chunk overlap (0–4999)">
              <n-input-number
                v-model:value="form.retrieval.chunk_overlap"
                class="num-input"
                :min="0"
                :max="4999"
                :step="1"
              />
            </n-form-item>
          </n-form>
          <div class="card-actions">
            <n-button
              type="primary"
              :loading="saving.retrieval"
              @click="saveGroup(groupRetrieval)"
            >
              保存检索
            </n-button>
          </div>
        </n-card>

        <!-- 路径与环境（需重启） -->
        <n-card class="card" :bordered="false">
          <template #header>
            <div class="card-head">
              <span class="card-title">路径与环境</span>
              <span class="badge restart">需重启</span>
            </div>
          </template>
          <n-form label-placement="left" :label-width="210">
            <n-form-item label="Documents dir">
              <n-input v-model:value="form.paths.documents_dir" />
            </n-form-item>
            <n-form-item label="Data dir">
              <n-input v-model:value="form.paths.data_dir" />
            </n-form-item>
            <n-form-item label="Chroma collection">
              <n-input v-model:value="form.paths.chroma_collection" />
            </n-form-item>
          </n-form>
          <div class="card-actions">
            <n-button type="primary" :loading="saving.paths" @click="saveGroup(groupPaths)">
              保存路径
            </n-button>
          </div>
        </n-card>

        <!-- Embedding 模型（需重启） -->
        <n-card class="card" :bordered="false">
          <template #header>
            <div class="card-head">
              <span class="card-title">Embedding 模型</span>
              <span class="badge restart">需重启</span>
            </div>
          </template>
          <n-form label-placement="left" :label-width="210">
            <n-form-item label="Model">
              <n-input v-model:value="form.embedding.model" />
            </n-form-item>
          </n-form>
          <div class="card-actions">
            <n-button
              type="primary"
              :loading="saving.embedding"
              @click="saveGroup(groupEmbedding)"
            >
              保存 Embedding
            </n-button>
          </div>
        </n-card>
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-heading {
  margin: 4px 0 0;
  font-size: 20px;
  font-weight: 700;
}

.restart-banner {
  border-radius: 10px;
}

.groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  box-shadow: var(--shadow-soft);
}

.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
}

.badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 9px;
  border-radius: 999px;
  white-space: nowrap;
}

.badge.hot {
  color: var(--ok);
  background: color-mix(in srgb, var(--ok) 13%, transparent);
}

.badge.restart {
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 15%, transparent);
}

.num-input {
  width: 220px;
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}

@media (max-width: 640px) {
  .num-input {
    width: 100%;
  }
}
</style>
