<script setup lang="ts">
// ============================================================================
// 根组件：Naive UI 全局配置（中文化 + 主题 token + 明暗）+ 全局 Provider。
// ============================================================================

import {
  darkTheme,
  dateZhCN,
  NConfigProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NMessageProvider,
  NNotificationProvider,
  zhCN,
  type GlobalThemeOverrides,
} from "naive-ui";
import { computed, onMounted } from "vue";

import { useChatStore } from "./stores/chat";
import { useHealthStore } from "./stores/health";
import { useThemeStore } from "./stores/theme";

const theme = useThemeStore();
const chat = useChatStore();
const health = useHealthStore();

theme.init();
chat.load();
onMounted(() => health.start());

const naiveTheme = computed(() => (theme.dark ? darkTheme : null));

const themeOverrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: "#4f6ef7",
    primaryColorHover: "#6b84f8",
    primaryColorPressed: "#3f5ce0",
    primaryColorSuppl: "#4f6ef7",
    borderRadius: "10px",
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif',
  },
  Card: { borderRadius: "14px" },
  Button: { borderRadiusMedium: "10px" },
  Input: { borderRadius: "10px" },
}));
</script>

<template>
  <n-config-provider
    abstract
    :theme="naiveTheme"
    :theme-overrides="themeOverrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
  >
    <n-loading-bar-provider>
      <n-message-provider>
        <n-notification-provider>
          <n-dialog-provider>
            <router-view />
          </n-dialog-provider>
        </n-notification-provider>
      </n-message-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>
