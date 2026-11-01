<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { http, errorText } from "@/api/client";
import { agentLabel, formatDate } from "@/api/types";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import MetricChart from "@/components/MetricChart.vue";
const overview = ref<Record<string, any> | null>(null);
const loading = ref(false);
const error = ref("");
const updatedAt = ref("");
const byAgent = computed<
  Array<{
    agent: string;
    total: number;
    failed: number;
    avg_latency_ms: number;
  }>
>(() => overview.value?.by_agent || []);
const services = computed(() => {
  const data = overview.value?.services;
  if (Array.isArray(data)) return data;
  return Object.entries(data || {}).map(([name, value]) => ({
    name,
    ...(typeof value === "object" && value ? value : { status: value }),
  }));
});
const failureLabels: Record<string, string> = {
  timeout: "调用超时",
  rate_limit: "服务限流",
  parse: "解析失败",
  budget: "预算超出",
  agent: "智能体失败",
  other: "其他",
};
function metric(value: unknown, suffix = "") {
  return value === null || value === undefined
    ? "—"
    : `${typeof value === "number" ? Math.round(value * 100) / 100 : value}${suffix}`;
}
function serviceLabel(status: unknown) {
  return status === "connected" || status === "configured" || status === true
    ? "已接入"
    : status === "not_connected" ||
        status === "not_configured" ||
        status === false
      ? "未接入"
      : status || "未知";
}
async function load() {
  loading.value = true;
  error.value = "";
  try {
    overview.value = (await http.get("/monitoring/overview/")).data;
    updatedAt.value = new Date().toISOString();
  } catch (err) {
    error.value = errorText(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div v-loading="loading">
    <div class="section-toolbar">
      <span class="muted"
        >{{
          overview?.scope === "all"
            ? "全局运行数据 · 管理员视图"
            : "我的运行数据"
        }}<template v-if="updatedAt">
          · 更新于 {{ formatDate(updatedAt) }}</template
        ></span
      ><el-button @click="load"
        ><AppIcon name="refresh" :size="15" /> 刷新数据</el-button
      >
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon /><template
      v-if="overview"
      ><section class="stat-grid">
        <article class="stat-card">
          <span class="stat-icon teal"><AppIcon name="pulse" /></span>
          <div>
            <span class="stat-label">智能体总调用</span
            ><strong>{{ metric(overview.agents?.total) }}</strong>
          </div>
        </article>
        <article class="stat-card">
          <span class="stat-icon blue"><AppIcon name="clock" /></span>
          <div>
            <span class="stat-label">检索平均延迟</span
            ><strong
              >{{ metric(overview.retrieval?.avg_latency_ms)
              }}<small>ms</small></strong
            >
          </div>
        </article>
        <article class="stat-card">
          <span class="stat-icon amber"><AppIcon name="clock" /></span>
          <div>
            <span class="stat-label">检索 P99 延迟</span
            ><strong
              >{{ metric(overview.retrieval?.p99_latency_ms)
              }}<small>ms</small></strong
            >
          </div>
        </article>
        <article class="stat-card">
          <span class="stat-icon violet"><AppIcon name="chart" /></span>
          <div>
            <span class="stat-label">检索无命中率</span
            ><strong>{{
              overview.retrieval?.no_hit_rate != null
                ? metric(overview.retrieval.no_hit_rate * 100, "%")
                : "—"
            }}</strong>
          </div>
        </article>
      </section>
      <div class="dashboard-grid">
        <section class="card">
          <div class="section-title">
            <div>
              <h2>智能体调用分布</h2>
              <p class="muted">按实际运行记录统计</p>
            </div>
            <span class="pill neutral">{{ byAgent.length }} 个智能体</span>
          </div>
          <MetricChart
            v-if="byAgent.length"
            :labels="byAgent.map((item) => agentLabel(item.agent))"
            :values="byAgent.map((item) => item.total)"
            unit="次"
          /><EmptyState
            v-else
            title="暂无运行记录"
            description="运行一次问诊后生成真实统计。"
          />
        </section>
        <section class="card">
          <div class="section-title">
            <h2>知识库与索引</h2>
            <span
              class="pill"
              :class="
                overview.knowledge?.status === 'not_connected' ? 'neutral' : ''
              "
              >{{ serviceLabel(overview.knowledge?.status) }}</span
            >
          </div>
          <dl class="metric-list">
            <div>
              <dt>去重后文档</dt>
              <dd>{{ metric(overview.knowledge?.documents) }}</dd>
            </div>
            <div>
              <dt>索引切片总数</dt>
              <dd>{{ metric(overview.knowledge?.chunks) }}</dd>
            </div>
            <div>
              <dt>最近索引时间</dt>
              <dd class="small">
                {{ formatDate(overview.knowledge?.last_indexed_at) }}
              </dd>
            </div>
            <div>
              <dt>检索接入状态</dt>
              <dd>{{ serviceLabel(overview.retrieval?.status) }}</dd>
            </div>
          </dl>
          <p class="muted small">
            未接入检索服务的指标显示为“—”，不以模拟数据填充。
          </p>
        </section>
      </div>
      <div class="dashboard-grid">
        <section class="card">
          <div class="section-title">
            <h2>质量反馈</h2>
            <AppIcon name="chat" :size="18" />
          </div>
          <div class="feedback-stats">
            <div>
              <strong>{{ metric(overview.feedback?.count) }}</strong
              ><span>总反馈</span>
            </div>
            <div>
              <strong>{{ metric(overview.feedback?.positive) }}</strong
              ><span>有帮助</span>
            </div>
            <div>
              <strong>{{ metric(overview.feedback?.negative) }}</strong
              ><span>需改进</span>
            </div>
          </div>
          <dl class="metric-list">
            <div>
              <dt>正向反馈率</dt>
              <dd>
                {{
                  overview.feedback?.positive_rate != null
                    ? metric(overview.feedback.positive_rate * 100, "%")
                    : "—"
                }}
              </dd>
            </div>
            <div>
              <dt>已记账模型费用</dt>
              <dd>
                {{ metric(overview.cost?.total) }}
                {{ overview.cost?.currency || "" }}
              </dd>
            </div>
          </dl>
        </section>
        <section class="card">
          <div class="section-title">
            <h2>失败模式</h2>
            <span class="pill neutral">{{ metric(overview.failures) }} 次</span>
          </div>
          <div v-if="overview.failure_modes?.length" class="failure-list">
            <div v-for="item in overview.failure_modes" :key="item.kind">
              <span
                ><i class="failure-dot"></i
                >{{ failureLabels[item.kind] || item.kind }}</span
              ><strong>{{ item.count }}</strong>
            </div>
          </div>
          <EmptyState v-else title="暂无失败事件记录" compact />
        </section>
      </div>
      <section class="card">
        <div class="section-title">
          <h2>智能体性能明细</h2>
          <span class="muted small">毫秒 · 按 Agent 聚合</span>
        </div>
        <el-table v-if="byAgent.length" :data="byAgent"
          ><el-table-column label="智能体" min-width="130"
            ><template #default="scope">{{
              agentLabel(scope.row.agent)
            }}</template></el-table-column
          ><el-table-column prop="total" label="调用次数" /><el-table-column
            prop="failed"
            label="失败次数"
          /><el-table-column label="平均延迟 (ms)"
            ><template #default="scope">{{
              metric(scope.row.avg_latency_ms)
            }}</template></el-table-column
          ></el-table
        ><EmptyState v-else title="暂无性能记录" compact />
      </section>
      <section v-if="services.length" class="card">
        <div class="section-title"><h2>服务接入状态</h2></div>
        <div class="service-grid">
          <div
            v-for="service in services"
            :key="service.name"
            class="service-item"
          >
            <strong>{{ service.name }}</strong
            ><span class="pill neutral">{{ serviceLabel(service.status) }}</span
            ><small v-if="service.detail" class="muted">{{
              service.detail
            }}</small>
          </div>
        </div>
      </section></template
    ><EmptyState v-else-if="!loading && !error" title="监控数据尚未接入" />
  </div>
</template>
