<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { http, errorText, resultList } from "@/api/client";
import { useSessionStore } from "@/stores/session";
import { formatDate } from "@/api/types";
import { type LearningOverview, type DataAsset, type TrainingRun, type TrainingEvent, type Evaluation, learningStatus, numberText, configText } from "@/api/learning";
import AppIcon from "@/components/AppIcon.vue";
import EmptyState from "@/components/EmptyState.vue";
import ProgressPipeline from "@/components/ProgressPipeline.vue";
import TrainingCurve from "@/components/TrainingCurve.vue";
import RagStatus from "@/components/RagStatus.vue";
const session = useSessionStore();
const route = useRoute(); const router = useRouter();
const staff = computed(() => !!session.user?.is_staff);
const overview = ref<LearningOverview | null>(null);
const assets = ref<DataAsset[]>([]); const runs = ref<TrainingRun[]>([]); const evaluations = ref<Evaluation[]>([]);
const selected = ref<TrainingRun | null>(null); const events = ref<TrainingEvent[]>([]);
const selectedId = ref(""); const cursor = ref(0); const loading = ref(false); const syncing = ref(false);
const error = ref(""); const logError = ref(""); const notice = ref("");
const versions = ref<Array<{id:string;label:string;run_id:string;adapter_path:string;sha256:string;is_active:boolean;validation_status?:string;created_at?:string}>>([]);
const activations = ref<Array<{id:number;previous_id:string|null;version_id:string|null;review_note:string;created_at?:string}>>([]);
const activeVersion = ref<string|null>(null); const versionBusy = ref("");
const previewAsset = ref<DataAsset|null>(null);
const preview = ref<{asset_key:string;fields:string[];results:Array<Record<string,unknown>>;sampled_rows:number;note:string}|null>(null);
const previewBusy = ref(false); const previewError = ref(""); let previewGeneration = 0;
const fieldLabel = (field: string) => ({query:"查询问题",positive:"相关答案 / 证据",negative:"不相关答案 / 证据",pos:"相关证据",neg:"不相关证据",code:"编码",name:"名称"} as Record<string,string>)[field] || field;
const registration = ref({run_id:"",label:"",adapter_path:""}); const activationNote = ref(""); const activationConfirmed = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined; let disposed = false; let generation = 0;
const progress = computed(() => typeof selected.value?.progress === "number" && Number.isFinite(selected.value.progress) ? Math.min(100, Math.max(0, selected.value.progress)) : null);
const model = computed(() => overview.value?.configuration?.model?.model_id);
const parameters = computed(() => overview.value?.selected_profile?.parameters || overview.value?.configuration?.train || {});
const visibleParameters = computed(() => Object.fromEntries(Object.entries(parameters.value).filter(([key]) => ["lr_scheduler_type", "weight_decay", "num_epochs", "early_stopping", "learning_rate", "per_device_batch_size", "gradient_accumulation_steps", "max_seq_length"].includes(key))));
const parameterLabels: Record<string, string> = { lr_scheduler_type: "学习率调度", weight_decay: "权重衰减", num_epochs: "训练轮数", early_stopping: "早停", learning_rate: "学习率", per_device_batch_size: "单卡批量", gradient_accumulation_steps: "梯度累积", max_seq_length: "序列长度", logging_steps: "日志间隔", seed: "随机种子", fp16: "FP16", bf16: "BF16" };
function seriesFor(keys: string[]) {
  return keys.map(key => ({ name: ({ loss: "训练 loss", eval_loss: "验证 loss", learning_rate: "学习率" } as Record<string, string>)[key] || key,
    points: events.value.filter(event => typeof event.step === "number" && typeof event.metrics?.[key] === "number" && Number.isFinite(event.metrics[key])).map(event => [event.step!, event.metrics[key]] as [number, number]) })).filter(series => series.points.length);
}
const lossSeries = computed(() => seriesFor(["loss", "eval_loss"])); const rateSeries = computed(() => seriesFor(["learning_rate"]));
function schedule() {
  clearTimeout(timer);
  if (!disposed && selected.value?.status === "running") timer = setTimeout(() => refreshSelected(), Number(import.meta.env.VITE_TRAINING_POLL_MS || 5000));
}
async function refreshSelected() {
  if (!selectedId.value || !staff.value) return;
  const id = selectedId.value; const token = generation;
  try {
    const [detail, log] = await Promise.all([http.get<TrainingRun>(`/learning/runs/${id}/`), http.get(`/learning/runs/${id}/events/`, { params: { after: cursor.value } })]);
    if (disposed || id !== selectedId.value || token !== generation) return;
    selected.value = detail.data;
    const incoming = resultList<TrainingEvent>(log.data);
    events.value = [...events.value, ...incoming.filter(event => !events.value.some(old => old.id === event.id))].slice(-500);
    cursor.value = log.data.next_cursor ?? cursor.value; logError.value = "";
  } catch (err) { if (id === selectedId.value) logError.value = errorText(err); }
  finally { schedule(); }
}
async function chooseRun(id: string) {
  ++generation; clearTimeout(timer); selectedId.value = id; cursor.value = 0; events.value = []; logError.value = "";
  selected.value = runs.value.find(run => run.id === id) || null;
  await router.replace({ query: { ...route.query, run: id || undefined } });
  await refreshSelected();
}
async function load() {
  if (!staff.value) return;
  loading.value = true; error.value = "";
  const responses = await Promise.allSettled([http.get<LearningOverview>("/learning/overview/"), http.get("/learning/datasets/"), http.get("/learning/runs/"), http.get("/learning/evaluations/"), http.get("/learning/models/")]);
  if (disposed) return;
  const failures: string[] = [];
  if (responses[0].status === "fulfilled") overview.value = responses[0].value.data; else failures.push(`训练配置：${errorText(responses[0].reason)}`);
  if (responses[1].status === "fulfilled") assets.value = resultList(responses[1].value.data); else failures.push(`数据资产：${errorText(responses[1].reason)}`);
  if (responses[2].status === "fulfilled") runs.value = resultList(responses[2].value.data); else failures.push(`运行记录：${errorText(responses[2].reason)}`);
  if (responses[3].status === "fulfilled") evaluations.value = resultList(responses[3].value.data); else failures.push(`检索评测：${errorText(responses[3].reason)}`);
  if (responses[4].status === "fulfilled") { versions.value = resultList(responses[4].value.data); activations.value = responses[4].value.data.activations || []; activeVersion.value = responses[4].value.data.active_id || null; } else failures.push(`模型版本：${errorText(responses[4].reason)}`);
  error.value = failures.join("；"); loading.value = false;
  const id = selectedId.value || (typeof route.query.run === "string" ? route.query.run : runs.value[0]?.id);
  if (id) { if (id !== selectedId.value) await chooseRun(id); else await refreshSelected(); }
}
async function sync() {
  syncing.value = true; notice.value = "";
  try { await http.post("/learning/sync/", {}); notice.value = "同步完成，已重新核验可访问的资产与日志。同步不会启动训练。"; await load(); }
  catch (err) { error.value = errorText(err); }
  finally { syncing.value = false; }
}
async function previewDataset(asset: DataAsset) {
  const token = ++previewGeneration; previewAsset.value = asset; preview.value = null; previewError.value = ""; previewBusy.value = true;
  try { const {data} = await http.get(`/learning/datasets/${encodeURIComponent(asset.key)}/preview/`, {params:{limit:3}}); if (!disposed && token === previewGeneration) preview.value = data; }
  catch (err) { if (!disposed && token === previewGeneration) previewError.value = errorText(err); }
  finally { if (token === previewGeneration) previewBusy.value = false; }
}
function closePreview() { ++previewGeneration; previewAsset.value = null; preview.value = null; previewError.value = ""; previewBusy.value = false; }
async function registerModel() {
  versionBusy.value = "register"; error.value = ""; notice.value = "";
  try { await http.post("/learning/models/register/", registration.value); await load(); notice.value = "模型产物已登记，仍须人工核对评测后登记为活动版本。"; }
  catch (err) { error.value = errorText(err); } finally { versionBusy.value = ""; }
}
async function activateModel(id: string) {
  versionBusy.value = id; error.value = ""; notice.value = "";
  try { await http.post(`/learning/models/${id}/activate/`, { review_note: activationNote.value, evidence_confirmed: activationConfirmed.value }); await load(); activationConfirmed.value = false; notice.value = "已登记活动版本与审校依据。使用此模型前须重建匹配索引，原登记可回滚。"; }
  catch (err) { error.value = errorText(err); } finally { versionBusy.value = ""; }
}
async function rollbackModel(id: number) {
  versionBusy.value = "rollback"; error.value = ""; notice.value = "";
  try { await http.post("/learning/models/rollback/", { activation_id: id, review_note: activationNote.value }); await load(); notice.value = "已回滚活动版本登记；索引版本不匹配时将阻断检索，请核对接入面板。"; }
  catch (err) { error.value = errorText(err); } finally { versionBusy.value = ""; }
}
onMounted(load); onBeforeUnmount(() => { disposed = true; ++generation; clearTimeout(timer); });
</script>
<template>
  <div class="learning-page">
    <EmptyState v-if="!staff" title="训练与数据仅对项目管理员开放" description="普通账号可以继续问诊并管理自己的反馈授权。" />
    <template v-else>
      <div class="learning-toolbar"><p>从数据来源到训练证据，把每次改进记录清楚。</p><div><el-button :loading="loading" @click="load"><AppIcon name="refresh" :size="15" />刷新</el-button><el-button type="primary" :loading="syncing" @click="sync">同步本机产物</el-button></div></div>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <el-alert v-if="notice" :title="notice" type="success" show-icon />
      <RagStatus />
      <section class="learning-metrics"><article class="card"><span>登记数据资产</span><strong>{{ numberText(overview?.datasets.total) }}<small>项</small></strong><p>文档登记与文件核验分别记录</p></article><article class="card"><span>文件已核验</span><strong>{{ numberText(overview?.datasets.verified) }}<small>项</small></strong><p>{{ numberText(overview?.datasets.missing) }} 项尚未找到本地文件</p></article><article class="card"><span>训练运行</span><strong>{{ numberText(overview?.training.runs) }}<small>次</small></strong><p>{{ numberText(overview?.training.active) }} 次正在执行</p></article></section>
      <section class="card"><div class="section-title"><div><h2>数据资产</h2><p class="muted">已报告规模不是本机实测规模，文件缺失时保持待接入。</p></div><span class="pill neutral">来源可追溯</span></div>
        <div v-if="assets.length" class="learning-table-scroll"><table class="learning-table"><thead><tr><th>数据 / 用途</th><th>文档报告行数</th><th>本机核验行数</th><th>文件状态</th><th>来源与文件</th><th>数据样例</th></tr></thead><tbody><tr v-for="asset in assets" :key="asset.id || asset.key"><td><strong>{{ asset.title }}</strong><small>{{ asset.format }}</small></td><td>{{ numberText(asset.reported_rows) }}</td><td>{{ numberText(asset.observed_rows) }}</td><td><span class="pill" :class="asset.file_status === 'verified' ? '' : 'neutral'">{{ learningStatus(asset.file_status) }}</span></td><td><span>{{ asset.source }}</span><small class="break-word">{{ asset.path }}</small><details v-if="asset.sha256"><summary>文件指纹</summary><code>{{ asset.sha256 }}</code></details></td><td><el-button size="small" :disabled="asset.file_status !== 'verified'" :loading="previewBusy && previewAsset?.key === asset.key" @click="previewDataset(asset)">查看样例</el-button></td></tr></tbody></table></div>
        <EmptyState v-else title="尚无数据登记" description="同步已配置的资产清单后，显示来源、声明规模与实际文件核验结果。" compact />
        <section v-if="previewAsset" class="asset-preview" aria-label="脱敏数据样例"><div class="section-title"><div><h3>{{ previewAsset.title }} · 前 {{ preview?.sampled_rows ?? '—' }} 条样例</h3><p class="muted">只请求少量样例，不读取全量文件；已自动遮盖常见身份标识，仍需人工复核。</p></div><el-button size="small" @click="closePreview">收起样例</el-button></div><el-alert v-if="previewError" :title="previewError" type="error" show-icon :closable="false" /><p v-if="previewBusy" class="learning-note">正在读取脱敏样例…</p><template v-if="preview"><p v-if="preview.note" class="learning-note">{{ preview.note }}</p><article v-for="(record,index) in preview.results" :key="index" class="asset-preview-record"><span class="pill neutral">样例 {{ index + 1 }}</span><dl><template v-for="field in preview.fields" :key="field"><dt>{{ fieldLabel(field) }}</dt><dd class="preserve">{{ configText(record[field]) }}</dd></template></dl></article><EmptyState v-if="!preview.results.length" title="文件中没有可展示的样例" compact /></template></section>
      </section>
      <div class="learning-two-column"><section class="card"><div class="section-title"><div><h2>当前选用配置</h2><p class="muted">由训练配置与选型记录读取</p></div><span class="pill neutral">{{ overview?.selected_profile?.label || '未登记' }}</span></div><h3 class="learning-model-name">{{ configText(model) }}</h3><dl class="learning-config"><template v-for="(value,key) in visibleParameters" :key="key"><dt>{{ parameterLabels[String(key)] || key }}</dt><dd>{{ configText(value) }}</dd></template></dl><details v-if="Object.keys(parameters).length" class="learning-config-details"><summary>完整配置与 LoRA 参数</summary><pre>{{ JSON.stringify(overview?.configuration,null,2) }}</pre></details><EmptyState v-if="!Object.keys(parameters).length" title="尚未读取训练配置" compact /></section>
      <section class="card"><div class="section-title"><div><h2>训练运行</h2><p class="muted">只有真实执行或导入记录才产生进度</p></div><span class="pill neutral">{{ runs.length }} 条</span></div><div v-if="runs.length" class="training-run-list"><button v-for="item in runs" :key="item.id" class="training-run-button" :class="{selected:selectedId === item.id}" @click="chooseRun(item.id)"><span><strong>{{ item.label }}</strong><small>{{ formatDate(item.updated_at) }}</small></span><span class="pill neutral">{{ learningStatus(item.status) }}</span></button></div><EmptyState v-else title="尚无训练日志" description="同学的训练记录接入后将在这里展示；当前不会模拟训练进度。" compact /><p class="learning-note">同步仅读取允许目录内的记录，不自动下载模型或占用 GPU。</p></section></div>
      <section v-if="selected" class="card training-detail"><div class="section-title"><div><h2>{{ selected.label }}</h2><p class="muted">{{ selected.source }} · 更新于 {{ formatDate(selected.updated_at) }}</p></div><span class="pill" :class="selected.status === 'failed' ? 'danger' : 'neutral'">{{ learningStatus(selected.status) }}</span></div><el-alert v-if="logError" :title="logError" type="error" show-icon :closable="false" />
        <p v-if="selected.provenance?.note" class="learning-note">来源说明：{{ selected.provenance.note }}</p><p v-if="selected.provenance?.stop_reason" class="learning-note">终止原因：{{ selected.provenance.stop_reason }}</p><details v-if="selected.config && Object.keys(selected.config).length" class="learning-config-details"><summary>此运行的配置快照（与当前配置分别记录）</summary><pre>{{ JSON.stringify(selected.config,null,2) }}</pre></details><p v-if="selected.status === 'early_stopped'" class="learning-note">此历史运行因早停结束，保留真实步数和比例，不补齐至 100%；不能当作当前选型配置的训练日志。</p>
        <div class="training-progress-summary"><span>记录步数 {{ numberText(selected.current_step) }} / {{ numberText(selected.total_steps) }}</span><span v-if="progress !== null">{{ progress.toFixed(1) }}%</span><span v-else>总步数或执行状态未确认，不估造百分比</span></div><el-progress v-if="progress !== null" :percentage="progress" :show-text="false" :status="selected.status === 'failed' ? 'exception' : undefined" />
        <dl v-if="Object.keys(selected.metrics || {}).length" class="training-metric-snapshot"><template v-for="(value,key) in selected.metrics" :key="key"><dt>{{ ({loss:"训练 loss",eval_loss:"验证 loss",best_eval_loss:"最佳验证 loss",learning_rate:"学习率"} as Record<string,string>)[String(key)] || key }}</dt><dd>{{ value }}</dd></template></dl>
        <ProgressPipeline v-if="selected.pipeline?.length" :stages="selected.pipeline" label="训练进度流水线" />
        <div class="learning-two-column curve-grid"><div><h3>训练与验证 loss</h3><TrainingCurve v-if="lossSeries.length" :series="lossSeries" /><EmptyState v-else title="尚无 loss 记录" compact /></div><div><h3>学习率变化</h3><TrainingCurve v-if="rateSeries.length" :series="rateSeries" /><EmptyState v-else title="尚无学习率记录" compact /></div></div>
        <div class="section-title"><h3>训练日志</h3><span class="muted small">保留最近 500 条显示记录 · 运行中自动刷新</span></div><ol v-if="events.length" class="training-log" aria-label="真实训练日志"><li v-for="event in events" :key="event.id"><time>{{ formatDate(event.created_at) }}</time><span>{{ event.level }} · {{ event.phase }}</span><p>{{ event.message || event.kind }}</p><code v-if="Object.keys(event.metrics || {}).length">{{ JSON.stringify(event.metrics) }}</code></li></ol><EmptyState v-else title="该运行尚无日志事件" description="不会用其他运行或示例日志补齐。" compact />
      </section>
      <section class="card"><div class="section-title"><div><h2>检索评测与模型选型</h2><p class="muted">先确认评测范围，再比较模型；报告与原始产物分开展示。</p></div><AppIcon name="chart" /></div><EmptyState v-if="!evaluations.length" title="尚无评测结果" description="接入评测 CSV 或有明确来源的实验报告后展示。" compact />
        <article v-for="evaluation in evaluations" :key="evaluation.id" class="evaluation-report"><div class="section-title"><h3>{{ evaluation.title }}</h3><span class="pill neutral">{{ evaluation.verified ? '原始文件已核验 · 未复跑' : '文档报告 · 尚未核验原始产物' }}</span></div><p class="learning-note">{{ evaluation.scope.kind === 'candidate_pool' ? '候选池评测，不能等同 Milvus 全库召回率' : evaluation.scope.kind }} · 查询 {{ numberText(evaluation.scope.queries) }} 条 · 每条 {{ numberText(evaluation.scope.positive) }} 正例 + {{ numberText(evaluation.scope.negative) }} 负例</p><p v-if="evaluation.scope.note" class="learning-note">{{ evaluation.scope.note }}</p><div class="learning-table-scroll"><table class="learning-table"><thead><tr><th>指标</th><th>基座</th><th>线性基线</th><th>余弦调优</th></tr></thead><tbody><tr v-for="metric in evaluation.metrics" :key="metric.metric"><th>{{ metric.metric }}</th><td>{{ metric.base == null ? '—' : metric.base.toFixed(4) }}</td><td>{{ metric.baseline == null ? '—' : metric.baseline.toFixed(4) }}</td><td>{{ metric.cosine == null ? '—' : metric.cosine.toFixed(4) }}</td></tr></tbody></table></div><p class="learning-note">选用记录：{{ evaluation.selected_model }} · 来源：{{ evaluation.source }}</p></article>
      </section>
      <section class="card"><div class="section-title"><div><h2>模型版本与活动登记</h2><p class="muted">活动版本与索引必须配套；当前实际使用情况以检索接入面板为准，版本不匹配会阻断向量检索。</p></div><span class="pill neutral">{{ activeVersion ? '已有活动登记' : '尚无活动登记' }}</span></div>
        <form class="model-registration" @submit.prevent="registerModel"><label>关联训练运行<select v-model="registration.run_id" aria-label="关联训练运行"><option value="">请选择真实运行</option><option v-for="item in runs" :key="item.id" :value="item.id">{{ item.label }} · {{ learningStatus(item.status) }}</option></select></label><label>版本名称<el-input v-model="registration.label" placeholder="填写可识别的版本名称" aria-label="模型版本名称" /></label><label>Adapter 产物路径<el-input v-model="registration.adapter_path" placeholder="配置允许目录内的实际产物" aria-label="Adapter产物路径" /></label><el-button native-type="submit" :disabled="!registration.run_id || !registration.label.trim() || !registration.adapter_path.trim()" :loading="versionBusy === 'register'">登记模型产物</el-button></form>
        <EmptyState v-if="!versions.length" title="尚无已登记模型" description="文件与匹配评测未核验时不能登记为活动版本。" compact />
        <template v-else><div class="learning-table-scroll"><table class="learning-table"><thead><tr><th>版本 / 来源</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="version in versions" :key="version.id"><td><strong>{{ version.label }}</strong><small class="break-word">{{ version.adapter_path }}</small><details><summary>产物指纹</summary><code>{{ version.sha256 }}</code></details></td><td>{{ version.is_active ? '当前活动登记' : version.validation_status === 'evaluated' ? '评测关联已核验' : '待核对模型与评测关联' }}</td><td><el-button size="small" :disabled="!!versionBusy || version.is_active || version.validation_status !== 'evaluated' || !activationNote.trim() || !activationConfirmed" @click="activateModel(version.id)">登记为活动版本</el-button></td></tr></tbody></table></div><div class="model-review"><el-input v-model="activationNote" placeholder="填写评测依据、登记或回滚原因" aria-label="模型版本审校说明" /><label class="learning-checkbox"><input v-model="activationConfirmed" type="checkbox" />已核对真实评测产物与模型版本，确认本次活动登记</label></div></template>
        <details v-if="activations.length" class="model-history"><summary>查看活动登记与回滚记录（{{ activations.length }}）</summary><article v-for="activation in activations" :key="activation.id"><p>{{ formatDate(activation.created_at) }} · {{ activation.review_note }}</p><el-button v-if="activation.version_id && activation.version_id === activeVersion" size="small" :disabled="!!versionBusy || !activationNote.trim()" @click="rollbackModel(activation.id)">{{ activation.previous_id ? '回滚此次登记' : '撤回活动登记' }}</el-button></article></details>
      </section>
    </template>
  </div>
</template>
