<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { http, errorText, resultList, websocketUrl } from "@/api/client";
import {
  agentLabel,
  formatDate,
  isRunActive,
  statusLabel,
  type Consultation,
  type Message,
  type Run,
} from "@/api/types";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import AgentTimeline from "@/components/AgentTimeline.vue";
import EvidenceList from "@/components/EvidenceList.vue";
import SoapPanel from "@/components/SoapPanel.vue";
import SafetyAudit from "@/components/SafetyAudit.vue";
const route = useRoute();
const router = useRouter();
const consultations = ref<Consultation[]>([]);
const consultation = ref<Consultation | null>(null);
const runs = ref<Run[]>([]);
const run = ref<Run | null>(null);
const input = ref("");
const search = ref("");
const busy = ref(false);
const loading = ref(false);
const error = ref("");
const historyError = ref("");
const historyPage = ref(1);
const historyHasMore = ref(false);
const historyBusy = ref(false);
const pendingRequest = ref<{
  consultationId: number;
  content: string;
  id: string;
} | null>(null);
const streamText = ref("");
const connection = ref("idle");
const conversationElement = ref<HTMLElement>();
const feedbackRating = ref<number | null>(null);
const feedbackComment = ref("");
const feedbackBusy = ref(false);
const feedbackSaved = ref(false);
const feedbackError = ref("");
let socket: WebSocket | null = null;
let poll: ReturnType<typeof setTimeout> | undefined;
let reconnect: ReturnType<typeof setTimeout> | undefined;
let generation = 0;
let disposed = false;
const currentId = computed(() => Number(route.params.id) || null);
const messages = computed(() => consultation.value?.messages || []);
const active = computed(() => isRunActive(run.value?.status));
const visibleHistory = computed(() =>
  consultations.value.filter((item) => item.title?.includes(search.value)),
);
const runError = computed(() =>
  typeof run.value?.error === "string"
    ? run.value.error
    : run.value?.error?.message,
);
const riskLabels: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "极高风险",
  extreme: "极高风险",
  very_high: "极高风险",
  unknown: "待评估",
};
const risk = computed(
  () =>
    riskLabels[consultation.value?.risk_level || "unknown"] ||
    consultation.value?.risk_level,
);
const citations = computed(() =>
  run.value
    ? run.value.reply?.citations || []
    : [...messages.value].reverse().find((m) => m.role === "assistant")
        ?.citations || [],
);
function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const h = Array.from(bytes, (n) => n.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
function stopTransport() {
  clearTimeout(poll);
  clearTimeout(reconnect);
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  connection.value = "idle";
}
async function scrollEnd() {
  await nextTick();
  conversationElement.value?.scrollTo({
    top: conversationElement.value.scrollHeight,
    behavior: "smooth",
  });
}
async function loadHistory(more = false) {
  if (historyBusy.value) return;
  historyBusy.value = true;
  const page = more ? historyPage.value + 1 : 1;
  try {
    const { data } = await http.get("/consultations/", { params: { page } });
    const items = resultList<Consultation>(data);
    consultations.value = more
      ? [
          ...consultations.value,
          ...items.filter(
            (item) =>
              !consultations.value.some((existing) => existing.id === item.id),
          ),
        ]
      : items;
    historyPage.value = page;
    historyHasMore.value = !!data.next;
    historyError.value = "";
  } catch (err) {
    historyError.value = errorText(err);
  } finally {
    historyBusy.value = false;
  }
}
async function refreshConsultation(id: number) {
  const { data } = await http.get<Consultation>(`/consultations/${id}/`);
  if (id === currentId.value) consultation.value = data;
}
async function refreshRun(id: number, runId: string) {
  try {
    const { data } = await http.get<Run>(`/consultations/${id}/runs/${runId}/`);
    if (id !== currentId.value || (run.value && run.value.run_id !== runId))
      return;
    error.value = "";
    run.value = data;
    if (!isRunActive(data.status)) {
      clearTimeout(poll);
      streamText.value = "";
      await refreshConsultation(id);
      await loadHistory();
      await scrollEnd();
    }
  } catch (err) {
    if (id === currentId.value) error.value = errorText(err);
  }
}
function startPolling(id: number, runId: string) {
  clearTimeout(poll);
  poll = setTimeout(
    async () => {
      if (disposed || id !== currentId.value) return;
      await refreshRun(id, runId);
      if (isRunActive(run.value?.status)) startPolling(id, runId);
    },
    Number(import.meta.env.VITE_RUN_POLL_MS || 2000),
  );
}
function connect(id: number) {
  if (socket) {
    socket.onclose = null;
    socket.close();
  }
  connection.value = "connecting";
  socket = new WebSocket(websocketUrl(id));
  socket.onopen = () => {
    if (id === currentId.value) connection.value = "connected";
  };
  socket.onerror = () => {
    if (id === currentId.value) connection.value = "disconnected";
  };
  socket.onclose = () => {
    if (disposed || id !== currentId.value) return;
    connection.value = "disconnected";
    reconnect = setTimeout(() => {
      if (!disposed && id === currentId.value) connect(id);
    }, 5000);
  };
  socket.onmessage = async (event) => {
    if (id !== currentId.value) return;
    try {
      const data = JSON.parse(event.data);
      if (run.value && data.run_id && data.run_id !== run.value.run_id) return;
      if (!run.value && data.run_id)
        run.value = {
          run_id: data.run_id,
          trace_id: data.trace_id || "",
          status: "running",
          steps: [],
        };
      if (data.type?.startsWith("agent.") && data.agent && run.value) {
        const steps = [...(run.value.steps || [])];
        const eventStatus = data.status || data.type.split(".")[1];
        const step = {
          agent: data.agent,
          status: eventStatus === "completed" ? "succeeded" : eventStatus,
          latency_ms: data.payload?.latency_ms,
          error_code: data.payload?.error_code,
        };
        const index = steps.findIndex((item) => item.agent === data.agent);
        if (index >= 0) steps[index] = { ...steps[index], ...step };
        else steps.push(step);
        run.value = { ...run.value, steps };
      }
      if (data.type === "answer.chunk") {
        streamText.value += data.payload?.text || "";
        await scrollEnd();
      }
      if (["run.completed", "run.failed"].includes(data.type) && data.run_id)
        await refreshRun(id, data.run_id);
    } catch {
      /* authoritative run polling recovers malformed or missed transport events */
    }
  };
}
async function select(id: number | null) {
  const token = ++generation;
  stopTransport();
  consultation.value = null;
  run.value = null;
  runs.value = [];
  streamText.value = "";
  error.value = "";
  feedbackSaved.value = false;
  feedbackRating.value = null;
  feedbackComment.value = "";
  feedbackError.value = "";
  if (!id) return;
  loading.value = true;
  try {
    const [detail, runList] = await Promise.all([
      http.get<Consultation>(`/consultations/${id}/`),
      http.get(`/consultations/${id}/runs/`),
    ]);
    if (token !== generation || disposed) return;
    consultation.value = detail.data;
    runs.value = resultList<Run>(runList.data);
    const requestedRun =
      typeof route.query.run === "string" ? route.query.run : "";
    run.value = requestedRun
      ? runs.value.find((item) => item.run_id === requestedRun) || null
      : runs.value[0] || null;
    connect(id);
    const runId = requestedRun || run.value?.run_id;
    if (runId) {
      await refreshRun(id, runId);
      if (isRunActive(run.value?.status)) startPolling(id, runId);
    }
    await scrollEnd();
  } catch (err) {
    if (token === generation) error.value = errorText(err);
  } finally {
    if (token === generation) loading.value = false;
  }
}
async function send() {
  const content = input.value.trim();
  if (!content || busy.value || active.value) return;
  busy.value = true;
  error.value = "";
  streamText.value = "";
  feedbackSaved.value = false;
  feedbackRating.value = null;
  try {
    let id = currentId.value;
    if (!id) {
      const created = (
        await http.post<Consultation>("/consultations/", {
          title: content.slice(0, 40),
        })
      ).data;
      id = created.id;
      await router.replace(`/consultation/${id}`);
      await select(id);
    }
    if (
      !pendingRequest.value ||
      pendingRequest.value.consultationId !== id ||
      pendingRequest.value.content !== content
    )
      pendingRequest.value = { consultationId: id, content, id: uuid() };
    const { data } = await http.post<Run>(`/consultations/${id}/runs/`, {
      content,
      client_request_id: pendingRequest.value.id,
    });
    pendingRequest.value = null;
    input.value = "";
    if (id === currentId.value) {
      run.value = data;
      runs.value = [
        data,
        ...runs.value.filter((item) => item.run_id !== data.run_id),
      ];
      await refreshConsultation(id);
      startPolling(id, data.run_id);
      await scrollEnd();
    }
    await loadHistory();
  } catch (err) {
    error.value = errorText(err);
  } finally {
    busy.value = false;
  }
}
async function chooseRun(value: string) {
  if (!currentId.value || active.value) return;
  run.value = runs.value.find((item) => item.run_id === value) || null;
  feedbackSaved.value = false;
  feedbackRating.value = null;
  feedbackComment.value = "";
  feedbackError.value = "";
  if (run.value) await refreshRun(currentId.value, value);
}
async function saveFeedback() {
  if (!currentId.value || !run.value || feedbackRating.value === null) return;
  feedbackBusy.value = true;
  feedbackError.value = "";
  try {
    await http.post(`/consultations/${currentId.value}/feedback/`, {
      run_id: run.value.run_id,
      rating: feedbackRating.value,
      comment: feedbackComment.value,
    });
    feedbackSaved.value = true;
  } catch (err) {
    feedbackError.value = errorText(err);
  } finally {
    feedbackBusy.value = false;
  }
}
function newConsultation() {
  input.value = "";
  router.push("/consultation");
}
watch(
  () => [currentId.value, route.query.run] as const,
  ([id]) => select(id),
  { immediate: true },
);
onMounted(() => loadHistory());
onBeforeUnmount(() => {
  disposed = true;
  ++generation;
  stopTransport();
});
</script>
<template>
  <div class="consultation-workspace">
    <aside class="history-panel card">
      <div class="section-title">
        <h2>我的问诊</h2>
        <button
          class="icon-button"
          aria-label="刷新会话列表"
          @click="loadHistory()"
        >
          <AppIcon name="refresh" :size="16" />
        </button>
      </div>
      <el-button type="primary" class="full-width" @click="newConsultation"
        ><AppIcon name="plus" :size="16" /> 新建问诊</el-button
      ><el-input
        v-model="search"
        placeholder="搜索当前列表"
        clearable
        class="history-search"
        aria-label="搜索会话"
      />
      <p v-if="historyError" class="text-danger small">{{ historyError }}</p>
      <div class="history-list">
        <RouterLink
          v-for="item in visibleHistory"
          :key="item.id"
          :to="`/consultation/${item.id}`"
          class="history-item"
          :class="{ selected: currentId === item.id }"
          ><strong>{{ item.title || "未命名问诊" }}</strong
          ><small>{{ formatDate(item.updated_at) }}</small></RouterLink
        ><EmptyState
          v-if="!visibleHistory.length"
          title="暂无会话"
          compact
        /><el-button
          v-if="historyHasMore"
          text
          class="full-width"
          :loading="historyBusy"
          @click="loadHistory(true)"
          >加载更多会话</el-button
        >
      </div>
    </aside>
    <section class="conversation-panel card" v-loading="loading">
      <div class="conversation-toolbar">
        <div>
          <h2>{{ consultation?.title || "开始新的健康对话" }}</h2>
          <span class="muted small">{{
            currentId ? `会话 #${currentId}` : "描述你的不适，系统会按需追问"
          }}</span>
        </div>
        <span
          v-if="consultation"
          class="pill"
          :class="
            ['high', 'critical', 'very_high', 'extreme'].includes(
              consultation.risk_level || '',
            )
              ? 'danger'
              : 'neutral'
          "
          >{{ risk }}</span
        >
      </div>
      <el-alert
        v-if="error || runError"
        :title="error || runError"
        type="error"
        show-icon
        :closable="false"
      />
      <div
        ref="conversationElement"
        class="conversation-messages"
        aria-live="polite"
      >
        <div v-if="!messages.length && !loading" class="chat-welcome">
          <span class="chat-welcome-symbol"
            ><AppIcon name="chat" :size="35"
          /></span>
          <h3>你好，今天感觉怎么样？</h3>
          <p>
            请描述症状、持续时间和变化。<br />如有过敏史、基础疾病或正在用药，也请一并说明。
          </p>
          <div class="chat-hints">
            <span>症状与持续时间</span><span>已有检查结果</span
            ><span>过敏及用药情况</span>
          </div>
          <p class="chat-warning">
            <AppIcon name="shield" :size="14" />
            如遇急重症，请立即寻求急诊帮助。
          </p>
        </div>
        <article
          v-for="message in messages"
          :key="message.id"
          class="message-row"
          :class="message.role === 'user' ? 'from-user' : 'from-assistant'"
        >
          <span class="message-avatar"
            ><AppIcon
              :name="message.role === 'user' ? 'chat' : 'agents'"
              :size="18"
          /></span>
          <div class="message-body">
            <div class="message-meta">
              <strong>{{ message.role === "user" ? "我" : "医协助手" }}</strong
              ><small>{{ formatDate(message.created_at) }}</small>
            </div>
            <div class="message-content preserve">{{ message.content }}</div>
            <details v-if="message.citations?.length" class="message-evidence">
              <summary>{{ message.citations.length }} 条引用证据</summary>
              <EvidenceList :citations="message.citations" />
            </details>
          </div>
        </article>
        <article v-if="streamText" class="message-row from-assistant">
          <span class="message-avatar"
            ><AppIcon name="shield" :size="18"
          /></span>
          <div class="message-body">
            <div class="message-meta">
              <strong>医协助手</strong><small>安全回复</small>
            </div>
            <div class="message-content preserve">{{ streamText }}</div>
          </div>
        </article>
        <div v-if="active && !streamText" class="thinking-line">
          <span class="loading-dot"></span> 智能体正在协作，请稍候…
        </div>
        <SafetyAudit
          v-if="!active && (run?.safety || run?.metadata?.safety)"
          :audit="(run?.safety || run?.metadata?.safety)!"
        />
        <section
          v-if="
            run &&
            !active &&
            (run.soap || run.plain_explanation || run.guidance)
          "
          class="result-summary"
        >
          <div class="section-title">
            <h3>结构化小结</h3>
            <span class="pill">SOAP</span>
          </div>
          <SoapPanel
            :soap="run.soap"
            :explanation="run.plain_explanation"
            :guidance="run.guidance"
          />
        </section>
        <section v-if="run?.reply && !active" class="feedback-panel">
          <div class="feedback-heading">
            <span>这次回答对你有帮助吗？</span>
            <div>
              <button
                class="feedback-button"
                :class="{ chosen: feedbackRating === 1 }"
                aria-label="有帮助"
                @click="
                  feedbackRating = 1;
                  feedbackSaved = false;
                "
              >
                有帮助 ＋</button
              ><button
                class="feedback-button"
                :class="{ chosen: feedbackRating === -1 }"
                aria-label="需改进"
                @click="
                  feedbackRating = -1;
                  feedbackSaved = false;
                "
              >
                需改进 −
              </button>
            </div>
          </div>
          <template v-if="feedbackRating !== null && !feedbackSaved"
            ><el-input
              v-model="feedbackComment"
              placeholder="可以补充原因（选填）"
              maxlength="2000"
            /><el-button
              size="small"
              :loading="feedbackBusy"
              @click="saveFeedback"
              >提交反馈</el-button
            ></template
          >
          <p v-if="feedbackSaved" class="success-text small">
            反馈已保存，谢谢你的参与。
          </p>
          <p v-if="feedbackError" class="text-danger small">
            {{ feedbackError }}
          </p>
        </section>
      </div>
      <form class="message-composer" @submit.prevent="send">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          :disabled="busy || active"
          placeholder="请输入症状、持续时间及相关情况…"
          aria-label="症状描述"
          @keydown.ctrl.enter.prevent="send"
        />
        <div class="composer-bottom">
          <span
            ><AppIcon name="shield" :size="13" />
            不输入姓名、证件号等身份信息</span
          ><el-button
            type="primary"
            native-type="submit"
            :loading="busy || active"
            :disabled="!input.trim()"
            size="default"
            >{{ active ? "协作中" : "发送" }}<AppIcon name="send" :size="15"
          /></el-button>
        </div>
      </form>
    </section>
    <aside class="trace-panel">
      <section class="card">
        <div class="section-title">
          <h2>协作进程</h2>
          <AppIcon name="pulse" :size="18" />
        </div>
        <div class="transport-status">
          <i :class="connection"></i
          >{{
            connection === "connected"
              ? "实时状态已连接"
              : connection === "disconnected"
                ? "连接重试中 · 自动查询恢复"
                : currentId
                  ? "正在建立实时连接"
                  : "新建会话后连接"
          }}
        </div>
        <el-select
          v-if="runs.length > 1"
          :model-value="run?.run_id"
          size="small"
          class="full-width run-select"
          :disabled="active"
          aria-label="选择运行记录"
          @change="chooseRun"
          ><el-option
            v-for="(item, index) in runs"
            :key="item.run_id"
            :label="`运行 ${runs.length - index} · ${statusLabel(item.status)}`"
            :value="item.run_id"
        /></el-select>
        <div v-if="run" class="run-status">
          <span class="pill" :class="run.status === 'failed' ? 'danger' : ''">{{
            statusLabel(run.status)
          }}</span
          ><span v-if="run.trace_id" class="trace-id" :title="run.trace_id"
            >Trace · {{ run.trace_id }}</span
          >
        </div>
        <AgentTimeline
          v-if="run?.steps?.length"
          :steps="run.steps"
        /><EmptyState
          v-else
          title="等待协作开始"
          description="真实调用状态将在这里依次呈现。"
          compact
        />
      </section>
      <section class="card">
        <div class="section-title">
          <h2>本次证据</h2>
          <span class="count-badge">{{ citations.length }}</span>
        </div>
        <EvidenceList
          v-if="citations.length"
          :citations="citations"
        /><EmptyState
          v-else
          title="暂无引用证据"
          description="未检索到的证据不会生成引用。"
          compact
        />
      </section>
      <div class="trace-safety">
        <AppIcon name="shield" :size="18" />
        <p>医疗内容经过安全审核后展示。信息仅供参考，请以执业医师意见为准。</p>
      </div>
    </aside>
  </div>
</template>
