<script setup lang="ts">
// ============================================================================
// 管理员账号管理：列表 + 新增 / 改密 / 解锁 / 删除。
// 所有错误统一 message.error(e.detail || e.message)。
// ============================================================================

import {
  NButton,
  NCard,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NTag,
  useDialog,
  useMessage,
  type DataTableColumns,
} from "naive-ui";
import { computed, h, onMounted, reactive, ref } from "vue";

import { adminApi, AdminApiError } from "../../api/admin";
import { useAdminStore } from "../../stores/admin";
import type { AdminAccount } from "../../types";
import { formatDateTime } from "../../utils/format";

const adminStore = useAdminStore();
const dialog = useDialog();
const message = useMessage();

const accounts = ref<AdminAccount[]>([]);
const loading = ref(false);

const meName = computed(() => adminStore.me?.username ?? "");

function errText(e: unknown): string {
  if (e instanceof AdminApiError) return e.detail || e.message;
  if (e instanceof Error) return e.message;
  return "网络错误，请稍后重试";
}

async function refresh() {
  loading.value = true;
  try {
    accounts.value = await adminApi<AdminAccount[]>("/accounts");
  } catch (e) {
    message.error(errText(e));
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refresh();
});

// ---------- 表格列 ----------
const columns: DataTableColumns<AdminAccount> = [
  {
    title: "用户名",
    key: "username",
    render(row) {
      return h("span", null, [
        row.username,
        row.username === meName.value ? h("small", { class: "self-mark" }, "（当前）") : null,
      ]);
    },
  },
  {
    title: "创建时间",
    key: "created_at",
    render: (row) => formatDateTime(row.created_at),
  },
  {
    title: "最后登录",
    key: "last_login_at",
    render: (row) => formatDateTime(row.last_login_at),
  },
  {
    title: "状态",
    key: "locked",
    width: 100,
    render(row) {
      return row.locked
        ? h(NTag, { type: "error", size: "small", bordered: false }, { default: () => "已锁定" })
        : h(NTag, { type: "success", size: "small", bordered: false }, { default: () => "正常" });
    },
  },
  {
    title: "操作",
    key: "actions",
    width: 210,
    render(row) {
      return h("div", { class: "row-actions" }, [
        h(
          NButton,
          { size: "small", quaternary: true, type: "primary", onClick: () => openEdit(row) },
          { default: () => "改密" },
        ),
        row.locked
          ? h(
              NButton,
              {
                size: "small",
                quaternary: true,
                type: "warning",
                onClick: () => void doUnlock(row),
              },
              { default: () => "解锁" },
            )
          : null,
        h(
          NButton,
          { size: "small", quaternary: true, type: "error", onClick: () => confirmDelete(row) },
          { default: () => "删除" },
        ),
      ]);
    },
  },
];

// ---------- 新增 ----------
const showAdd = ref(false);
const addSaving = ref(false);
const addForm = reactive({ username: "", password: "", confirm: "" });

function openAdd() {
  addForm.username = "";
  addForm.password = "";
  addForm.confirm = "";
  showAdd.value = true;
}

async function submitAdd() {
  const u = addForm.username.trim();
  if (!u || !addForm.password) {
    message.error("请填写用户名和密码");
    return;
  }
  if (addForm.password !== addForm.confirm) {
    message.error("两次密码不一致");
    return;
  }
  addSaving.value = true;
  try {
    await adminApi("/accounts", { method: "POST", body: { username: u, password: addForm.password } });
    message.success("已创建");
    showAdd.value = false;
    await refresh();
  } catch (e) {
    message.error(errText(e));
  } finally {
    addSaving.value = false;
  }
}

// ---------- 改密 ----------
const showEdit = ref(false);
const editSaving = ref(false);
const editTarget = ref<AdminAccount | null>(null);
const editForm = reactive({ oldPassword: "", password: "", confirm: "" });

const editIsSelf = computed(
  () => !!editTarget.value && editTarget.value.username === meName.value,
);

function openEdit(row: AdminAccount) {
  editTarget.value = row;
  editForm.oldPassword = "";
  editForm.password = "";
  editForm.confirm = "";
  showEdit.value = true;
}

async function submitEdit() {
  const target = editTarget.value;
  if (!target) return;
  if (!editForm.password) {
    message.error("请输入新密码");
    return;
  }
  if (editForm.password !== editForm.confirm) {
    message.error("两次密码不一致");
    return;
  }
  if (editIsSelf.value && !editForm.oldPassword) {
    message.error("请输入原密码");
    return;
  }
  editSaving.value = true;
  try {
    const body: { new_password: string; old_password?: string } = {
      new_password: editForm.password,
    };
    if (editForm.oldPassword) body.old_password = editForm.oldPassword;
    await adminApi(`/accounts/${target.id}`, { method: "PATCH", body });
    message.success("已保存");
    showEdit.value = false;
    await refresh();
  } catch (e) {
    message.error(errText(e));
  } finally {
    editSaving.value = false;
  }
}

// ---------- 解锁 ----------
async function doUnlock(row: AdminAccount) {
  try {
    await adminApi(`/accounts/${row.id}`, { method: "PATCH", body: { unlock: true } });
    message.success("已解锁");
    await refresh();
  } catch (e) {
    message.error(errText(e));
  }
}

// ---------- 删除 ----------
function confirmDelete(row: AdminAccount) {
  dialog.warning({
    title: "删除账号？",
    content: `确认删除账号 ${row.username}？此操作不可撤销。`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await adminApi(`/accounts/${row.id}`, { method: "DELETE" });
        message.success("已删除");
        await refresh();
      } catch (e) {
        message.error(errText(e));
      }
    },
  });
}
</script>

<template>
  <div class="accounts-page">
    <div class="page-head">
      <h1 class="page-heading">账号管理</h1>
      <n-button type="primary" @click="openAdd">＋ 新增管理员</n-button>
    </div>

    <n-card class="card" :bordered="false">
      <n-data-table
        :columns="columns"
        :data="accounts"
        :loading="loading"
        :bordered="false"
        :single-line="false"
      />
    </n-card>

    <!-- 新增管理员 -->
    <n-modal
      v-model:show="showAdd"
      preset="card"
      title="新增管理员"
      :style="{ width: 'min(420px, 92vw)', borderRadius: '16px' }"
      :mask-closable="!addSaving"
    >
      <n-form @submit.prevent="submitAdd">
        <n-form-item label="用户名">
          <n-input
            v-model:value="addForm.username"
            placeholder="3-32 位小写字母 / 数字 / _ / -"
            autocomplete="off"
          />
        </n-form-item>
        <n-form-item label="密码">
          <n-input
            v-model:value="addForm.password"
            type="password"
            show-password-on="click"
            placeholder="至少 6 个字符"
            autocomplete="new-password"
          />
        </n-form-item>
        <n-form-item label="确认密码">
          <n-input
            v-model:value="addForm.confirm"
            type="password"
            show-password-on="click"
            placeholder="再次输入密码"
            autocomplete="new-password"
            @keyup.enter="submitAdd"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button :disabled="addSaving" @click="showAdd = false">取消</n-button>
          <n-button type="primary" :loading="addSaving" @click="submitAdd">创建</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 修改密码 -->
    <n-modal
      v-model:show="showEdit"
      preset="card"
      title="修改密码"
      :style="{ width: 'min(420px, 92vw)', borderRadius: '16px' }"
      :mask-closable="!editSaving"
    >
      <n-form @submit.prevent="submitEdit">
        <n-form-item label="用户名">
          <n-input :value="editTarget?.username ?? ''" disabled />
        </n-form-item>
        <n-form-item v-if="editIsSelf" label="原密码">
          <n-input
            v-model:value="editForm.oldPassword"
            type="password"
            show-password-on="click"
            placeholder="修改自己的密码需验证原密码"
            autocomplete="current-password"
          />
        </n-form-item>
        <n-form-item label="新密码">
          <n-input
            v-model:value="editForm.password"
            type="password"
            show-password-on="click"
            placeholder="至少 6 个字符"
            autocomplete="new-password"
          />
        </n-form-item>
        <n-form-item label="确认新密码">
          <n-input
            v-model:value="editForm.confirm"
            type="password"
            show-password-on="click"
            placeholder="再次输入新密码"
            autocomplete="new-password"
            @keyup.enter="submitEdit"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button :disabled="editSaving" @click="showEdit = false">取消</n-button>
          <n-button type="primary" :loading="editSaving" @click="submitEdit">保存</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.page-heading {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.card {
  border-radius: 14px;
  box-shadow: var(--shadow-soft);
  transition: box-shadow 0.18s ease;
}

.card:hover {
  box-shadow: var(--shadow-pop);
}

.self-mark {
  margin-left: 6px;
  color: var(--fg-muted);
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
