<script setup lang="ts">
// ============================================================================
// 管理后台登录页：居中品牌卡片 + 登录表单，成功后跳转 redirect。
// 鉴权跳转（已登录访问本页 → /admin）由路由守卫处理。
// ============================================================================

import { NAlert, NButton, NForm, NFormItem, NInput } from "naive-ui";
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAdminStore } from "../../stores/admin";

const adminStore = useAdminStore();
const router = useRouter();
const route = useRoute();

const username = ref("");
const password = ref("");
const loading = ref(false);
const errorMsg = ref("");

async function submit() {
  if (loading.value) return;
  errorMsg.value = "";
  if (!username.value.trim() || !password.value) {
    errorMsg.value = "请输入用户名和密码";
    return;
  }
  loading.value = true;
  try {
    const err = await adminStore.login(username.value.trim(), password.value);
    if (err) {
      errorMsg.value = err;
      return;
    }
    const redirect =
      typeof route.query.redirect === "string" && route.query.redirect.startsWith("/")
        ? route.query.redirect
        : "/admin";
    await router.push(redirect);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="logo" aria-hidden="true">🎓</div>
      <h1 class="title">AI 辅导员 · 管理后台</h1>
      <p class="subtitle">请使用管理员账号登录</p>

      <n-alert v-if="errorMsg" type="error" class="error-alert" :bordered="false">
        {{ errorMsg }}
      </n-alert>

      <n-form @submit.prevent="submit">
        <n-form-item :show-label="false">
          <n-input
            v-model:value="username"
            size="large"
            placeholder="用户名"
            autocomplete="username"
            :disabled="loading"
          />
        </n-form-item>
        <n-form-item :show-label="false">
          <n-input
            v-model:value="password"
            size="large"
            type="password"
            show-password-on="click"
            placeholder="密码"
            autocomplete="current-password"
            :disabled="loading"
            @keyup.enter="submit"
          />
        </n-form-item>
        <n-button
          type="primary"
          size="large"
          block
          attr-type="submit"
          :loading="loading"
          :disabled="loading"
        >
          登 录
        </n-button>
      </n-form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--bg);
  position: relative;
  overflow: hidden;
}

/* 品牌渐变装饰光斑 */
.login-page::before,
.login-page::after {
  content: "";
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  pointer-events: none;
}

.login-page::before {
  width: 460px;
  height: 460px;
  background: var(--brand-from);
  opacity: 0.16;
  top: -140px;
  left: -100px;
}

.login-page::after {
  width: 420px;
  height: 420px;
  background: var(--brand-to);
  opacity: 0.14;
  bottom: -140px;
  right: -80px;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 380px;
  max-width: 100%;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 18px;
  box-shadow: var(--shadow-pop);
  padding: 36px 32px 32px;
}

.logo {
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  border-radius: 16px;
  background: var(--brand-grad);
  display: grid;
  place-items: center;
  font-size: 28px;
  box-shadow: 0 6px 18px rgba(79, 110, 247, 0.35);
}

.title {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
  text-align: center;
}

.subtitle {
  margin: 8px 0 22px;
  font-size: 13px;
  color: var(--fg-muted);
  text-align: center;
}

.error-alert {
  margin-bottom: 16px;
  border-radius: 10px;
}
</style>
