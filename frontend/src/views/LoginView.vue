<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "@/stores/session";
import { errorText } from "@/api/client";
import AppIcon from "@/components/AppIcon.vue";
import MedicalScene from "@/components/MedicalScene.vue";
import { workspaceBackgroundStyle } from "@/config/workspace";
const backgroundStyle = workspaceBackgroundStyle();
const username = ref("");
const password = ref("");
const busy = ref(false);
const error = ref("");
const route = useRoute();
const router = useRouter();
const session = useSessionStore();
async function submit() {
  if (!username.value.trim() || !password.value) {
    error.value = "请输入账号和密码。";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    await session.login(username.value.trim(), password.value);
    const redirect =
      typeof route.query.redirect === "string" &&
      route.query.redirect.startsWith("/") &&
      !route.query.redirect.startsWith("//")
        ? route.query.redirect
        : "/";
    await router.replace(redirect);
  } catch (err) {
    error.value = errorText(err);
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="login-page" :style="backgroundStyle">
    <div class="workspace-backdrop" aria-hidden="true"></div>
    <div class="login-card">
      <section class="login-intro">
        <RouterLink to="/" class="brand"><span class="brand-symbol"><AppIcon name="plus" :size="25" /></span><span class="brand-wordmark">医协<small>医疗智能体协作平台</small></span></RouterLink>
        <div class="login-statement"><h1>让健康问题，<br />多一份清晰的答案。</h1><p>医学证据、专职智能体与安全审核相互协作，<br />把复杂信息，转化为你能理解的健康参考。</p></div>
        <MedicalScene scene="consultation" />
      </section>
      <section class="login-form-wrap"><form class="login-form" @submit.prevent="submit"><h2>登录协作工作台</h2><p class="muted">使用你的项目账号继续</p><el-alert v-if="error || route.query.connection" :title="error || '暂时无法连接后端，请确认服务地址与运行状态。'" type="error" show-icon :closable="false" /><label for="username">账号</label><el-input id="username" v-model="username" autocomplete="username" placeholder="请输入账号" size="large" /><label for="password">密码</label><el-input id="password" v-model="password" type="password" show-password autocomplete="current-password" placeholder="请输入密码" size="large" /><el-button class="login-submit" type="primary" native-type="submit" :loading="busy" size="large">进入工作台 <AppIcon name="arrow" :size="18" /></el-button><div class="login-hint"><AppIcon name="shield" :size="15" /><span>仅供健康信息参考，不替代医生诊断与治疗。<br />请勿输入真实患者的身份信息。</span></div></form></section>
    </div>
  </div>
</template>
