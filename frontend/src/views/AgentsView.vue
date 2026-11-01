<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { http, errorText, resultList, ApiError } from "@/api/client";
import {
  agentLabel,
  formatDate,
  statusLabel,
  type AgentInfo,
  type AgentStep,
} from "@/api/types";
import { useSessionStore } from "@/stores/session";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import AgentTimeline from "@/components/AgentTimeline.vue";
import SafetyAudit from "@/components/SafetyAudit.vue";
const route = useRoute();
const router = useRouter();
const session = useSessionStore();
const agents = ref<AgentInfo[]>([]);
const runs = ref<
  Array<{
    id: number;
    agent_name: string;
    status: string;
    trace_id: string;
    latency_ms: number;
    created_at: string;
  }>
>([]);
const selectedName = ref(String(route.params.name || ""));
const debateEnabled = ref<boolean | null>(null);
const llmConfigured = ref<boolean | null>(null);
const loading = ref(false);
const testBusy = ref(false);
const error = ref("");
const testError = ref("");
const content = ref("");
const result = ref<{
  reply?: unknown;
  steps?: AgentStep[];
  trace_id?: string;
  status?: string;
  safety?: Record<string, unknown> | null;
  metadata?: { safety?: Record<string, unknown> | null };
} | null>(null);
const selected = computed(() =>
  agents.value.find((agent) => agent.name === selectedName.value),
);
const selectedRuns = computed(() =>
  runs.value.filter((run) => run.agent_name === selectedName.value),
);
const resultText = computed(() =>
  typeof result.value?.reply === "string"
    ? result.value.reply
    : result.value?.reply &&
        typeof result.value.reply === "object" &&
        "content" in result.value.reply
      ? String(result.value.reply.content)
      : JSON.stringify(result.value?.reply, null, 2),
);
const resultDetails = computed(() => JSON.stringify(result.value, null, 2));
async function load() {
  loading.value = true;
  error.value = "";
  const results = await Promise.allSettled([
    http.get("/agents/"),
    http.get("/agents/runs/"),
  ]);
  if (results[0].status === "fulfilled") {
    agents.value = results[0].value.data.agents || [];
    debateEnabled.value = results[0].value.data.debate_enabled;
    llmConfigured.value = results[0].value.data.llm_configured ?? null;
    if (!selectedName.value) selectedName.value = agents.value[0]?.name || "";
  } else error.value = errorText(results[0].reason);
  if (results[1].status === "fulfilled")
    runs.value = resultList(results[1].value.data);
  else
    error.value = [error.value, `运行记录：${errorText(results[1].reason)}`]
      .filter(Boolean)
      .join("；");
  loading.value = false;
}
async function test() {
  if (!selected.value || !content.value.trim() || !session.user?.is_staff)
    return;
  testBusy.value = true;
  testError.value = "";
  result.value = null;
  try {
    result.value = (
      await http.post(
        `/agents/${encodeURIComponent(selected.value.name)}/test/`,
        { content: content.value.trim() },
      )
    ).data;
  } catch (err) {
    testError.value = errorText(err);
    if (err instanceof ApiError && err.details?.trace_id)
      result.value = {
        status: String(err.details.status || "failed"),
        trace_id: String(err.details.trace_id),
        steps: Array.isArray(err.details.steps) ? err.details.steps : [],
      };
  } finally {
    testBusy.value = false;
  }
}
function select(name: string) {
  selectedName.value = name;
  result.value = null;
  testError.value = "";
  router.replace(`/agents/${encodeURIComponent(name)}`);
}
watch(
  () => route.params.name,
  (name) => {
    if (name) selectedName.value = String(name);
  },
);
onMounted(load);
</script>
<template>
  <div v-loading="loading">
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <el-alert
      v-if="llmConfigured === false"
      title="模型服务尚未配置。请联系项目管理员完成配置后，再进行真实问诊与能力测试。"
      type="warning"
      show-icon
      :closable="false"
    />
    <div class="section-toolbar">
      <p class="muted">
        已注册 <strong>{{ agents.length }}</strong> 个智能体 · 辩论机制
        <span class="success-text">{{
          debateEnabled == null
            ? "状态未知"
            : debateEnabled
              ? "已启用"
              : "已关闭"
        }}</span>
      </p>
      <el-button @click="load"
        ><AppIcon name="refresh" :size="15" /> 刷新</el-button
      >
    </div>
    <div class="agents-workspace">
      <aside class="agent-selector">
        <button
          v-for="agent in agents"
          :key="agent.name"
          class="agent-selector-item"
          :class="{ selected: selectedName === agent.name }"
          @click="select(agent.name)"
        >
          <span class="agent-selector-icon"
            ><AppIcon
              :name="
                agent.name === 'safety'
                  ? 'shield'
                  : agent.name === 'retrieval'
                    ? 'book'
                    : 'agents'
              " /></span
          ><span
            ><strong>{{ agent.label || agentLabel(agent.name) }}</strong
            ><small>{{ agent.name }}</small></span
          ><AppIcon name="arrow" :size="16" /></button
        ><EmptyState v-if="!agents.length" title="暂无注册智能体" compact />
      </aside>
      <div v-if="selected" class="agent-detail">
        <section class="card">
          <div class="agent-detail-heading">
            <span class="large-agent-icon"
              ><AppIcon name="agents" :size="27"
            /></span>
            <div>

              <h2>{{ selected.label || agentLabel(selected.name) }}</h2>
            </div>
            <span class="pill neutral">{{
              selected.enabled === false ? "已关闭" : "已注册"
            }}</span>
          </div>
          <p class="agent-description">
            {{ selected.description || "此智能体尚未提供能力描述。" }}
          </p>
          <p class="muted small">
            运行标识：{{ selected.name }}
          </p>
        </section>
        <section class="card">
          <div class="section-title">
            <div>
              <h2>独立能力测试</h2>
              <p class="muted">输入测试上下文，查看实际输出与调用链</p>
            </div>
            <span class="pill neutral">管理员功能</span>
          </div>
          <el-alert
            v-if="!session.user?.is_staff"
            title="独立测试仅对项目管理员开放。你仍可在问诊中使用智能体协作功能。"
            type="info"
            :closable="false"
          />
          <form v-else @submit.prevent="test">
            <label class="field-label" for="agent-test-content">测试输入</label
            ><el-input
              id="agent-test-content"
              v-model="content"
              type="textarea"
              :rows="5"
              placeholder="请输入该智能体所需的症状、上下文或待审核内容。测试会调用后端配置的真实模型。"
            />
            <div class="test-actions">
              <span class="muted small"
                >调用可能产生模型费用，请避免敏感信息。</span
              ><el-button
                type="primary"
                native-type="submit"
                :loading="testBusy"
                :disabled="!content.trim()"
                >运行测试 <AppIcon name="arrow" :size="16"
              /></el-button>
            </div>
          </form>
          <el-alert
            v-if="testError"
            :title="testError"
            type="error"
            show-icon
          />
          <div v-if="result" class="test-result">
            <div class="section-title">
              <h3>运行结果</h3>
              <span
                class="pill"
                :class="result.status === 'failed' ? 'danger' : ''"
                >{{ statusLabel(result.status) }}</span
              >
            </div>
            <p v-if="result.trace_id" class="trace-id">
              Trace · {{ result.trace_id }}
            </p>
            <SafetyAudit
              v-if="result.safety || result.metadata?.safety"
              :audit="(result.safety || result.metadata?.safety)!"
            />
            <pre class="json-output">{{
              resultText || "运行未返回回复正文。"
            }}</pre>
            <AgentTimeline v-if="result.steps?.length" :steps="result.steps" />
            <details class="message-evidence">
              <summary>查看完整结构化结果</summary>
              <pre class="json-output">{{ resultDetails }}</pre>
            </details>
          </div>
        </section>
        <section class="card">
          <div class="section-title">
            <h2>最近运行</h2>
            <span class="muted small">当前账号可见记录</span>
          </div>
          <el-table v-if="selectedRuns.length" :data="selectedRuns" stripe
            ><el-table-column label="状态" width="105"
              ><template #default="scope"
                ><span
                  class="pill"
                  :class="scope.row.status === 'failed' ? 'danger' : 'neutral'"
                  >{{ statusLabel(scope.row.status) }}</span
                ></template
              ></el-table-column
            ><el-table-column
              prop="latency_ms"
              label="延迟 (ms)"
              width="115"
            /><el-table-column
              prop="trace_id"
              label="Trace"
              min-width="160"
              show-overflow-tooltip
            /><el-table-column label="时间" min-width="165"
              ><template #default="scope">{{
                formatDate(scope.row.created_at)
              }}</template></el-table-column
            ></el-table
          ><EmptyState
            v-else
            title="暂无运行记录"
            description="完成一次问诊后，可在此查看真实调用记录。"
            compact
          />
        </section>
      </div>
      <section v-else-if="agents.length" class="card">
        <EmptyState
          title="未找到该智能体"
          description="请从左侧选择已注册的智能体。"
        />
      </section>
    </div>
  </div>
</template>
