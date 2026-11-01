<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { http, errorText, resultList } from "@/api/client";
import { agentLabel, formatDate, type AgentInfo, type Consultation } from "@/api/types";
import { collaborationFlow } from "@/config/workspace";
import { useSessionStore } from "@/stores/session";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import MetricChart from "@/components/MetricChart.vue";
import MedicalScene from "@/components/MedicalScene.vue";
const session = useSessionStore();
const overview = ref<Record<string, any> | null>(null);
const consultations = ref<Consultation[]>([]);
const agents = ref<AgentInfo[]>([]);
const llmConfigured = ref<boolean | null>(null);
const agentsLoaded = ref(false);
const errors = ref<string[]>([]);
const loading = ref(true);
const updatedAt = ref("");
const byAgent = computed<Array<{ agent: string; total: number; failed: number; avg_latency_ms?: number }>>(() => overview.value?.by_agent || []);
const totalRuns = computed(() => overview.value?.agents?.total);
const failedRuns = computed(() => overview.value?.agents?.failed);
const feedback = computed(() => overview.value?.feedback);
const number = (value: unknown) => typeof value === "number" ? value.toLocaleString("zh-CN") : "—";
async function load() {
  loading.value = true; errors.value = [];
  const responses = await Promise.allSettled([http.get("/monitoring/overview/"), http.get("/consultations/"), http.get("/agents/")]);
  if (responses[0].status === "fulfilled") overview.value = responses[0].value.data;
  else errors.value.push(`运行概览：${errorText(responses[0].reason)}`);
  if (responses[1].status === "fulfilled") consultations.value = resultList<Consultation>(responses[1].value.data).slice(0, 3);
  else errors.value.push(`历史会话：${errorText(responses[1].reason)}`);
  if (responses[2].status === "fulfilled") { agents.value = responses[2].value.data.agents || []; llmConfigured.value = responses[2].value.data.llm_configured ?? null; agentsLoaded.value = true; }
  else errors.value.push(`智能体：${errorText(responses[2].reason)}`);
  updatedAt.value = new Date().toISOString(); loading.value = false;
}
onMounted(load);
</script>
<template>
  <div class="home-page" v-loading="loading">
    <el-alert v-for="error in errors" :key="error" :title="error" type="error" show-icon />
    <div class="home-intro-grid">
      <section class="home-hero" aria-labelledby="home-title"><div class="home-hero-copy"><span class="scene-page-label">你好，{{ session.displayName }}</span><h1 id="home-title">多一份协作，<br />让判断更有依据。</h1><p>从症状描述、医学检索到通俗解释，<br />把每一步协作，变成看得懂的健康指引。</p><div class="hero-actions"><RouterLink to="/consultation"><el-button type="primary" size="large">开始问诊 <AppIcon name="arrow" :size="17" /></el-button></RouterLink><RouterLink to="/agents" class="secondary-link">了解协作能力 <AppIcon name="arrow" :size="15" /></RouterLink></div><div class="hero-values"><span><AppIcon name="book" :size="14" /> 循证参考</span><span><AppIcon name="chat" :size="14" /> 白话解释</span><span><AppIcon name="shield" :size="14" /> 安全审核</span></div></div><MedicalScene scene="home" /></section>
      <aside class="card home-status-card"><div class="section-title"><h2>工作状态</h2><button class="icon-button" aria-label="刷新工作状态" @click="load"><AppIcon name="refresh" :size="16" /></button></div><div class="home-service-status"><div><span>模型服务</span><strong :class="llmConfigured === true ? 'status-ready' : 'status-waiting'"><i></i>{{ llmConfigured == null ? '状态未知' : llmConfigured ? '已配置' : '未配置' }}</strong></div><div><span>医学知识库</span><strong :class="overview?.knowledge?.status === 'connected' ? 'status-ready' : 'status-waiting'"><i></i>{{ overview?.knowledge?.status === 'connected' ? '已接入' : overview?.knowledge?.status === 'not_connected' ? '未接入' : '状态未知' }}</strong></div></div><div class="recent-heading"><h3>最近问诊</h3><RouterLink to="/consultation" class="text-link">全部 <AppIcon name="arrow" :size="13" /></RouterLink></div><div v-if="consultations.length" class="recent-list"><RouterLink v-for="item in consultations" :key="item.id" :to="`/consultation/${item.id}`" class="recent-row"><span class="recent-icon"><AppIcon name="chat" :size="16" /></span><div><strong>{{ item.title || '未命名问诊' }}</strong><small>{{ formatDate(item.updated_at) }}</small></div><AppIcon name="arrow" :size="14" /></RouterLink></div><EmptyState v-else title="还没有问诊记录" description="从一次对话开始，记录你的健康问题。" compact /></aside>
    </div>
    <section class="stat-grid home-stats"><article class="stat-card"><span class="stat-icon teal"><AppIcon name="agents" /></span><div><span class="stat-label">已注册协作能力</span><strong>{{ agentsLoaded ? agents.length : '—' }}<small v-if="agentsLoaded">项</small></strong></div><RouterLink to="/agents" aria-label="查看智能体" class="stat-link"><AppIcon name="arrow" :size="15" /></RouterLink></article><article class="stat-card"><span class="stat-icon blue"><AppIcon name="pulse" /></span><div><span class="stat-label">{{ overview?.scope === 'all' ? '全部' : '我的' }}智能体调用</span><strong>{{ number(totalRuns) }}<small v-if="totalRuns != null">次</small></strong></div></article><article class="stat-card"><span class="stat-icon amber"><AppIcon name="book" /></span><div><span class="stat-label">知识库文档</span><strong>{{ number(overview?.knowledge?.documents) }}<small v-if="overview?.knowledge?.documents != null">份</small></strong></div></article><article class="stat-card"><span class="stat-icon violet"><AppIcon name="clock" /></span><div><span class="stat-label">平均调用延迟</span><strong>{{ overview?.latency_ms?.avg != null ? Math.round(overview.latency_ms.avg).toLocaleString('zh-CN') : '—' }}<small>ms</small></strong></div></article></section>
    <div class="home-analysis-grid"><section class="card home-chart-card"><div class="section-title"><div><h2>智能体调用分布</h2><p class="muted">{{ overview?.scope === 'all' ? '全局' : '当前账号' }}运行记录</p></div><RouterLink to="/monitoring" class="text-link">运行监控 <AppIcon name="arrow" :size="14" /></RouterLink></div><MetricChart v-if="byAgent.length" :labels="byAgent.map(item => agentLabel(item.agent))" :values="byAgent.map(item => item.total)" unit="次" /><EmptyState v-else title="尚无调用记录" description="完成问诊后，真实调用分布将在这里呈现。" compact /></section><section class="card home-quality-card"><div class="section-title"><h2>协作与反馈</h2><AppIcon name="shield" :size="17" /></div><div class="quality-overview"><div><span>累计用户反馈</span><strong>{{ number(feedback?.count) }}</strong></div><div><span>正向反馈率</span><strong>{{ feedback?.positive_rate != null ? `${Math.round(feedback.positive_rate * 100)}%` : '—' }}</strong></div></div><div class="quality-detail"><div><span>有帮助</span><strong>{{ number(feedback?.positive) }}</strong></div><div><span>需改进</span><strong>{{ number(feedback?.negative) }}</strong></div><div><span>失败调用</span><strong>{{ number(failedRuns) }}</strong></div></div><div class="home-update-row"><span>{{ updatedAt ? `更新于 ${formatDate(updatedAt)}` : '等待数据更新' }}</span><RouterLink to="/monitoring" class="text-link">查看明细</RouterLink></div></section></div>
    <section class="card collaboration-card"><div class="section-title"><div class="flow-title"><h2>一次问诊，如何协作</h2><span class="pill neutral">流程示意</span></div><RouterLink to="/agents" class="text-link">进入智能体中心 <AppIcon name="arrow" :size="14" /></RouterLink></div><ol class="collaboration-flow"><li v-for="(stage, index) in collaborationFlow" :key="stage.id"><span class="flow-stage-number">{{ String(index + 1).padStart(2, '0') }}</span><span class="flow-stage-icon"><AppIcon :name="stage.icon" :size="21" /></span><h3>{{ stage.title }}</h3><p>{{ stage.description }}</p><div class="flow-stage-links"><template v-for="(agent, agentIndex) in stage.agents" :key="agent.name"><span v-if="agentIndex" class="parallel-symbol" aria-label="并行">∥</span><RouterLink :to="`/agents/${agent.name}`">{{ agent.label }} <AppIcon name="arrow" :size="11" /></RouterLink></template></div></li></ol></section>
  </div>
</template>
