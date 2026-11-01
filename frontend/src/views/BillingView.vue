<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { http, errorText } from "@/api/client";
import { agentLabel, formatDate } from "@/api/types";
import { useSessionStore } from "@/stores/session";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import MetricChart from "@/components/MetricChart.vue";
const session = useSessionStore();
const usage = ref<Record<string, any> | null>(null);
const budget = ref<Record<string, any> | null>(null);
const loading = ref(false);
const error = ref("");
const scope = ref("own");
const currency = computed(
  () => usage.value?.currency || budget.value?.currency || "",
);
const byDay = computed<Array<{ date: string; tokens: number; cost: string }>>(
  () => usage.value?.by_day || [],
);
const progress = computed(() =>
  budget.value?.token_limit
    ? Math.min(
        100,
        Math.round((budget.value.tokens_used / budget.value.token_limit) * 100),
      )
    : 0,
);
async function load() {
  loading.value = true;
  error.value = "";
  const results = await Promise.allSettled([
    http.get("/billing/usage/", { params: { scope: scope.value } }),
    http.get("/billing/budget/"),
  ]);
  if (results[0].status === "fulfilled") usage.value = results[0].value.data;
  else error.value = errorText(results[0].reason);
  if (results[1].status === "fulfilled") budget.value = results[1].value.data;
  else
    error.value = [error.value, errorText(results[1].reason)]
      .filter(Boolean)
      .join("；");
  loading.value = false;
}
onMounted(load);
</script>
<template>
  <div v-loading="loading">
    <div class="section-toolbar">
      <p class="muted">区分输入与输出 token，以实际调用记录汇总</p>
      <el-select
        v-if="session.user?.is_staff"
        v-model="scope"
        style="width: 145px; margin-left: auto"
        aria-label="账单数据范围"
        @change="load"
        ><el-option label="我的用量" value="own" /><el-option
          label="全部用户用量"
          value="all" /></el-select
      ><el-button @click="load"
        ><AppIcon name="refresh" :size="15" /> 刷新账单</el-button
      >
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon /><el-alert
      v-if="budget && !budget.price_configured"
      title="模型价格尚未配置。未定价调用不代表免费，配置价格后方可进行完整计费验收。"
      type="warning"
      show-icon
      :closable="false"
    />
    <section class="stat-grid">
      <article class="stat-card">
        <span class="stat-icon teal"><AppIcon name="bill" /></span>
        <div>
          <span class="stat-label">今日已记账费用 {{ currency }}</span
          ><strong>{{ usage?.today?.cost ?? "—" }}</strong>
        </div>
      </article>
      <article class="stat-card">
        <span class="stat-icon blue"><AppIcon name="pulse" /></span>
        <div>
          <span class="stat-label">今日 token</span
          ><strong>{{ usage?.today?.tokens?.toLocaleString() ?? "—" }}</strong>
        </div>
      </article>
      <article class="stat-card">
        <span class="stat-icon violet"><AppIcon name="chart" /></span>
        <div>
          <span class="stat-label">累计费用 {{ currency }}</span
          ><strong>{{ usage?.total?.cost ?? "—" }}</strong>
        </div>
      </article>
      <article class="stat-card">
        <span class="stat-icon amber"><AppIcon name="book" /></span>
        <div>
          <span class="stat-label">用量流水</span
          ><strong>{{ usage?.records ?? "—" }}<small>条</small></strong>
        </div>
      </article>
    </section>
    <div class="dashboard-grid">
      <section class="card">
        <div class="section-title">
          <div>
            <h2>每日费用</h2>
            <p class="muted">
              {{ currency ? `单位：${currency}` : "币种尚未配置" }}
            </p>
          </div>
        </div>
        <MetricChart
          v-if="byDay.length"
          :labels="byDay.map((item) => item.date)"
          :values="byDay.map((item) => Number(item.cost))"
          :unit="` ${currency}`"
        /><EmptyState
          v-else
          title="暂无费用记录"
          description="真实模型调用完成并记账后，这里会显示费用。"
        />
      </section>
      <section class="card">
        <div class="section-title">
          <h2>我的每日预算</h2>
          <span class="pill neutral">{{
            budget?.configured ? "已配置" : "未配置"
          }}</span>
        </div>
        <dl class="metric-list">
          <div>
            <dt>日期</dt>
            <dd>{{ budget?.date || "—" }}</dd>
          </div>
          <div>
            <dt>费用上限</dt>
            <dd>
              {{ budget?.cost_limit ?? "未配置" }}
              {{ budget?.cost_limit ? currency : "" }}
            </dd>
          </div>
          <div>
            <dt>剩余费用</dt>
            <dd>
              {{ budget?.remaining_cost ?? "—" }}
              {{ budget?.remaining_cost ? currency : "" }}
            </dd>
          </div>
          <div>
            <dt>预占费用</dt>
            <dd>{{ budget?.reserved_cost ?? "—" }} {{ currency }}</dd>
          </div>
          <div>
            <dt>token 上限</dt>
            <dd>{{ budget?.token_limit?.toLocaleString() ?? "未配置" }}</dd>
          </div>
          <div>
            <dt>已用 / 预占 token</dt>
            <dd>
              {{ budget?.tokens_used?.toLocaleString() ?? "—" }} /
              {{ budget?.reserved_tokens?.toLocaleString() ?? "—" }}
            </dd>
          </div>
        </dl>
        <el-progress
          v-if="budget?.token_limit"
          :percentage="progress"
          :stroke-width="6"
          :color="progress >= 90 ? '#c4772d' : '#198b81'"
        />
        <p v-if="!budget?.configured" class="muted small">
          预算尚未启用，请由管理员配置后验收超支拦截。
        </p>
      </section>
    </div>
    <section v-if="usage" class="card">
      <div class="section-title">
        <h2>token 与计量来源</h2>
        <span class="muted small">供应商返回与估算记录分别标记</span>
      </div>
      <div class="token-breakdown">
        <div>
          <span>累计输入 token</span
          ><strong>{{
            usage.total?.input_tokens?.toLocaleString() ?? "—"
          }}</strong>
        </div>
        <div>
          <span>累计输出 token</span
          ><strong>{{
            usage.total?.output_tokens?.toLocaleString() ?? "—"
          }}</strong>
        </div>
        <div>
          <span>供应商计量记录</span
          ><strong>{{ usage.measurement?.provider ?? "—" }}</strong>
        </div>
        <div>
          <span>估算记录</span
          ><strong>{{ usage.measurement?.estimated ?? "—" }}</strong>
        </div>
      </div>
    </section>
    <section class="card">
      <el-alert
        v-if="usage?.measurement?.legacy"
        title="包含历史未校准的计量记录，不能视为供应商精确账单。"
        type="info"
        :closable="false"
      />
      <div class="section-title">
        <h2>最近调用流水</h2>
        <span class="muted small">金额以调用时的价格快照计算</span>
      </div>
      <el-table v-if="usage?.latest?.length" :data="usage.latest"
        ><el-table-column label="智能体" min-width="110"
          ><template #default="scope">{{
            agentLabel(scope.row.agent || "unknown")
          }}</template></el-table-column
        ><el-table-column
          prop="model"
          label="模型"
          min-width="135"
          show-overflow-tooltip
        /><el-table-column label="查询运行 ID" min-width="145"
          ><template #default="scope"
            ><code :title="scope.row.run_id">{{
              scope.row.run_id ? `${scope.row.run_id.slice(0, 8)}…` : "—"
            }}</code></template
          ></el-table-column
        ><el-table-column
          prop="tokens_in"
          label="输入 token"
          min-width="100"
        /><el-table-column
          prop="tokens_out"
          label="输出 token"
          min-width="100"
        /><el-table-column
          prop="cost"
          :label="`费用 ${currency}`"
          min-width="120"
        /><el-table-column label="计量" width="105"
          ><template #default="scope"
            ><span class="pill neutral">{{
              scope.row.measurement === "provider"
                ? "供应商"
                : scope.row.measurement === "estimated"
                  ? "估算"
                  : scope.row.measurement === "legacy"
                    ? "历史未校准"
                    : "待核准"
            }}</span></template
          ></el-table-column
        ><el-table-column label="时间" min-width="170"
          ><template #default="scope">{{
            formatDate(scope.row.created_at)
          }}</template></el-table-column
        ></el-table
      ><EmptyState
        v-else
        title="暂无调用流水"
        description="未产生用量记录时，不生成模拟账单。"
        compact
      />
    </section>
    <section v-if="usage" class="card">
      <div class="section-title">
        <div>
          <h2>按单次查询汇总</h2>
          <p class="muted">
            同一会话的每次运行分别计费，聚合该次运行的全部智能体调用
          </p>
        </div>
      </div>
      <el-table
        v-if="usage.by_run?.length"
        :data="usage.by_run"
        class="single-run-billing-table"
      >
        <el-table-column label="查询运行 ID" min-width="155"
          ><template #default="scope"
            ><code :title="scope.row.run_id"
              >{{ scope.row.run_id.slice(0, 8) }}…</code
            ></template
          ></el-table-column
        >
        <el-table-column label="所属会话" min-width="140"
          ><template #default="scope"
            ><RouterLink
              v-if="scope.row.consultation_id"
              :to="{
                path: `/consultation/${scope.row.consultation_id}`,
                query: { run: scope.row.run_id },
              }"
              class="text-link"
              >会话 #{{ scope.row.consultation_id }} ↗</RouterLink
            ><span v-else>独立测试</span></template
          ></el-table-column
        >
        <el-table-column prop="tokens" label="token" min-width="100" />
        <el-table-column
          prop="cost"
          :label="`费用 ${currency}`"
          min-width="120"
        />
      </el-table>
      <EmptyState
        v-else
        title="暂无单次查询账单"
        description="具有运行 ID 的真实调用记录将在这里分别汇总。"
        compact
      />
    </section>
    <section v-if="usage?.by_query?.length" class="card">
      <div class="section-title"><h2>按问诊汇总</h2></div>
      <el-table :data="usage.by_query"
        ><el-table-column label="问诊"
          ><template #default="scope"
            ><RouterLink
              v-if="scope.row.consultation_id"
              :to="`/consultation/${scope.row.consultation_id}`"
              class="text-link"
              >会话 #{{ scope.row.consultation_id }}</RouterLink
            ><span v-else>独立测试</span></template
          ></el-table-column
        ><el-table-column prop="tokens" label="token" /><el-table-column
          prop="cost"
          :label="`费用 ${currency}`"
      /></el-table>
    </section>
    <section
      v-if="session.user?.is_staff && usage?.by_user?.length"
      class="card"
    >
      <div class="section-title">
        <h2>按用户汇总</h2>
        <span class="pill neutral">管理员视图</span>
      </div>
      <el-table :data="usage.by_user"
        ><el-table-column prop="username" label="账号" /><el-table-column
          prop="tokens"
          label="token" /><el-table-column
          prop="cost"
          :label="`费用 ${currency}`"
      /></el-table>
    </section>
  </div>
</template>
