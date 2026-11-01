<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "@/stores/session";
import { errorText } from "@/api/client";
import { pageDefinition, workspaceBackgroundStyle } from "@/config/workspace";
import AppIcon from "@/components/AppIcon.vue";
import WorkspaceNavigation from "@/components/WorkspaceNavigation.vue";
import PageScene from "@/components/PageScene.vue";
import PlatformBrand from "@/components/PlatformBrand.vue";
const route = useRoute();
const router = useRouter();
const session = useSessionStore();
const logoutError = ref("");
const page = computed(() => pageDefinition(route.name));
const backgroundStyle = workspaceBackgroundStyle();
async function logout() {
  try { await session.logout(); await router.replace("/login"); }
  catch (error) { logoutError.value = errorText(error); }
}
</script>
<template>
  <div class="app-shell" :style="backgroundStyle">
    <div class="workspace-backdrop" aria-hidden="true"></div>
    <header class="workspace-header"><div class="workspace-header-inner">
      <PlatformBrand />
      <WorkspaceNavigation :active-page="page.name" />
      <div class="workspace-user"><span class="avatar">{{ session.displayName.slice(0, 1).toUpperCase() }}</span><span class="user-name">{{ session.displayName }}<small>{{ session.user?.is_staff ? "项目管理员" : "个人账号" }}</small></span><button class="icon-button" title="退出登录" aria-label="退出登录" @click="logout"><AppIcon name="logout" :size="17" /></button></div>
    </div></header>
    <main class="app-main"><el-alert v-if="logoutError" :title="logoutError" type="error" show-icon /><PageScene v-if="page.name !== 'home'" :page="page" /><RouterView /></main>
    <footer class="app-footer"><AppIcon name="shield" :size="14" /><span>仅供技术演示与健康信息参考，不替代医生诊断、处方或急诊服务。</span></footer>
  </div>
</template>
