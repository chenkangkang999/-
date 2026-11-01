<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { http, errorText, resultList } from "@/api/client";
import { useSessionStore } from "@/stores/session";
import { formatDate } from "@/api/types";
import { type FlywheelOverview, type FeedbackCandidate, type TrainingBatch, type PreparedTraining, learningStatus, numberText } from "@/api/learning";
import EmptyState from "@/components/EmptyState.vue";
import AppIcon from "@/components/AppIcon.vue";
const session = useSessionStore(); const staff = computed(() => !!session.user?.is_staff);
const overview = ref<FlywheelOverview | null>(null); const candidates = ref<FeedbackCandidate[]>([]); const batches = ref<TrainingBatch[]>([]);
const selected = ref<FeedbackCandidate | null>(null); const chosenIds = ref<number[]>([]); const batchLabel = ref("");
const loading = ref(false); const busy = ref(""); const error = ref(""); const notice = ref("");
const prepared = ref<PreparedTraining | null>(null); const exportFormat = ref("triplets"); const exportSplit = ref("train");
const form = reactive({ positive: "", negative: "", positive_source: "", negative_source: "", review_note: "", redaction_confirmed: false, evidence_confirmed: false });
const flow = computed(() => [
  { title: "用户反馈", count: overview.value?.feedback_total, caption: "评价质量信号" },
  { title: "授权与脱敏", count: overview.value?.consented, caption: "用户明确允许回流" },
  { title: "人工审校", count: overview.value?.pending, caption: "待核对查询和证据" },
  { title: "可用训练对", count: overview.value?.approved, caption: "相关与不相关证据已确认" },
  { title: "冻结数据批次", count: overview.value?.batches, caption: "去重、划分与指纹" },
  { title: "训练准备", count: overview.value?.training_requests, caption: "BGE 配置与运行接入" },
]);
const commandLine = computed(() => prepared.value?.command?.length ? `& ${prepared.value.command.map(arg => `'${String(arg).replace(/'/g, "''")}'`).join(" ")}` : "");
function choose(candidate: FeedbackCandidate) {
  selected.value = candidate;
  Object.assign(form, { positive: candidate.positive || "", negative: candidate.negative || "", positive_source: candidate.positive_source || "", negative_source: candidate.negative_source || "", review_note: candidate.review_note || "", redaction_confirmed: false, evidence_confirmed: false });
}
async function load() {
  if (!staff.value) return;
  loading.value = true; error.value = "";
  const responses = await Promise.allSettled([http.get<FlywheelOverview>("/learning/flywheel/overview/"), http.get("/learning/flywheel/candidates/"), http.get("/learning/flywheel/batches/")]);
  const failures: string[] = [];
  if (responses[0].status === "fulfilled") overview.value = responses[0].value.data; else failures.push(errorText(responses[0].reason));
  if (responses[1].status === "fulfilled") {
    candidates.value = resultList(responses[1].value.data);
    if (selected.value) { const latest = candidates.value.find(item => item.id === selected.value?.id); if (latest) choose(latest); else selected.value = null; }
    chosenIds.value = chosenIds.value.filter(id => candidates.value.some(item => item.id === id && item.consent && item.status === "approved"));
  } else failures.push(`样本：${errorText(responses[1].reason)}`);
  if (responses[2].status === "fulfilled") batches.value = resultList(responses[2].value.data); else failures.push(`批次：${errorText(responses[2].reason)}`);
  error.value = failures.join("；"); loading.value = false;
}
async function collect() {
  busy.value = "collect"; error.value = ""; notice.value = "";
  try { const { data } = await http.post("/learning/flywheel/collect/", {}); await load(); notice.value = `已收集 ${numberText(data.created)} 条新候选，更新 ${numberText(data.updated)} 条。仅有授权的反馈进入审校，不自动生成训练标签。`; }
  catch (err) { error.value = errorText(err); } finally { busy.value = ""; }
}
async function review(decision: "approve" | "reject") {
  if (!selected.value) return;
  busy.value = decision; error.value = ""; notice.value = "";
  try { await http.post(`/learning/flywheel/candidates/${selected.value.id}/review/`, { decision, ...form }); await load(); notice.value = decision === "approve" ? "审校已通过，可选择该候选创建训练批次。" : "已拒绝该候选，不会用于训练。"; }
  catch (err) { error.value = errorText(err); } finally { busy.value = ""; }
}
async function createBatch() {
  if (!chosenIds.value.length) return;
  busy.value = "batch"; error.value = ""; notice.value = "";
  try { const { data } = await http.post<TrainingBatch>("/learning/flywheel/batches/", { candidate_ids: chosenIds.value, label: batchLabel.value }); await load(); chosenIds.value = []; notice.value = `已冻结批次“${data.label}”，共 ${numberText(data.sample_count)} 条。训练与验证按查询分组，避免同一问题泄漏。`; }
  catch (err) { error.value = errorText(err); } finally { busy.value = ""; }
}
async function download(batch: TrainingBatch) {
  busy.value = `download-${batch.id}`; error.value = "";
  try { const response = await http.get(`/learning/flywheel/batches/${batch.id}/download/`, { params: { format: exportFormat.value, split: exportSplit.value }, responseType: "blob" });
    const url = URL.createObjectURL(response.data); const link = document.createElement("a"); link.href = url; link.download = `bge-${batch.id}-${exportSplit.value}-${exportFormat.value}.jsonl`; link.click(); URL.revokeObjectURL(url);
    notice.value = "训练数据已下载；请仅在本机授权训练环境使用，不要上传含用户反馈的文件到公开仓库。";
  } catch (err) { error.value = errorText(err); } finally { busy.value = ""; }
}
async function prepare(batch: TrainingBatch) {
  busy.value = `prepare-${batch.id}`; error.value = ""; notice.value = ""; prepared.value = null;
  try { prepared.value = (await http.post<PreparedTraining>(`/learning/flywheel/batches/${batch.id}/prepare/`, {})).data; }
  catch (err) { error.value = errorText(err); } finally { busy.value = ""; }
}
async function copyCommand() {
  try { await navigator.clipboard.writeText(commandLine.value); notice.value = "训练命令已复制。执行前请确认使用现有 GPU 环境。"; }
  catch { error.value = "无法访问剪贴板，请手动选取命令复制。"; }
}
onMounted(load);
</script>
<template>
  <div class="learning-page flywheel-page">
    <EmptyState v-if="!staff" title="数据飞轮仅对项目管理员开放" description="你仍可以在问诊回答下提交评价，并选择或撤回训练授权。" />
    <template v-else>
      <div class="learning-toolbar"><p>把有依据的反馈，变成下一轮检索改进的起点。</p><div><el-button :loading="loading" @click="load"><AppIcon name="refresh" :size="15" />刷新</el-button><el-button type="primary" :loading="busy === 'collect'" @click="collect">收集已授权反馈</el-button></div></div>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <el-alert v-if="notice" :title="notice" type="success" show-icon />
      <section class="card"><div class="section-title"><div><h2>反馈回流流水线</h2><p class="muted">每个数字对应实际记录，阶段之间不表示自动通过。</p></div><span class="pill neutral">人工确认后改进</span></div><ol class="flywheel-overview-flow"><li v-for="(stage,index) in flow" :key="stage.title"><span>{{ String(index + 1).padStart(2,'0') }}</span><h3>{{ stage.title }}</h3><strong>{{ numberText(stage.count) }}</strong><p>{{ stage.caption }}</p></li></ol><div class="learning-notice"><AppIcon name="shield" :size="19" /><p>赞 / 踩只代表反馈，不等同检索正负标签。仅使用已授权、脱敏、人工核对的证据训练 BGE；网页不会自动启动 GPU 训练。授权撤回后，尚未训练的相关批次将禁止导出与准备。</p></div></section>
      <div class="flywheel-review-grid"><section class="card"><div class="section-title"><div><h2>反馈候选池</h2><p class="muted">待审 {{ numberText(overview?.pending) }} · 已撤回 {{ numberText(overview?.revoked) }}</p></div></div><EmptyState v-if="!candidates.length" title="还没有可审校的反馈" description="用户同意回流后，点击收集已授权反馈；没有证据的候选仍需人工补充。" compact />
        <ul v-else class="candidate-list"><li v-for="candidate in candidates" :key="candidate.id" :class="{selected:selected?.id === candidate.id}"><input v-if="candidate.status === 'approved' && candidate.consent" v-model="chosenIds" type="checkbox" :value="candidate.id" :aria-label="`选择训练候选 ${candidate.id}`" /><button @click="choose(candidate)"><span class="pill neutral">{{ learningStatus(candidate.status) }}</span><strong>{{ candidate.query }}</strong><small>{{ candidate.rating === 1 ? '有帮助' : '需改进' }} · {{ candidate.consent ? '已授权' : '已撤回授权' }} · {{ formatDate(candidate.updated_at) }}</small></button></li></ul>
        <div class="batch-composer"><label for="batch-label">批次名称（选填）</label><el-input id="batch-label" v-model="batchLabel" placeholder="记录本轮改进目的" maxlength="120" /><el-button type="primary" :disabled="!chosenIds.length || !!busy" :loading="busy === 'batch'" @click="createBatch">冻结所选 {{ chosenIds.length }} 条训练候选</el-button></div>
      </section>
      <section class="card"><div class="section-title"><div><h2>证据审校</h2><p class="muted">相关证据与不相关证据都需要来源，不能使用未核实的模型回答。</p></div></div><EmptyState v-if="!selected" title="选择一条反馈开始审校" description="通过前确认授权、脱敏与证据标签。" compact />
        <template v-else><dl class="candidate-facts"><dt>脱敏后的问题</dt><dd class="preserve">{{ selected.query }}</dd><dt>用户补充</dt><dd class="preserve">{{ selected.comment || '无补充' }}</dd></dl><details v-if="selected.citations?.length" class="candidate-citations"><summary>查看原检索证据（{{ selected.citations.length }}）</summary><article v-for="(citation,index) in selected.citations" :key="index"><strong>{{ citation.title || citation.id }}</strong><p>{{ citation.snippet || citation.content }}</p><code>{{ citation.source_url || citation.source || citation.url }}</code></article></details>
        <form class="evidence-review-form" @submit.prevent="review('approve')"><fieldset :disabled="!selected.consent || !!busy"><label for="positive-evidence">相关证据（positive）</label><el-input id="positive-evidence" v-model="form.positive" type="textarea" :rows="3" placeholder="经人工核对、能回答这个检索问题的证据" /><label for="positive-source">相关证据来源</label><el-input id="positive-source" v-model="form.positive_source" placeholder="文档 / 切片 ID 或可追溯来源" /><label for="negative-evidence">不相关证据（negative）</label><el-input id="negative-evidence" v-model="form.negative" type="textarea" :rows="3" placeholder="与问题不相关的证据，不能直接用用户的差评代替" /><label for="negative-source">不相关证据来源</label><el-input id="negative-source" v-model="form.negative_source" placeholder="文档 / 切片 ID 或可追溯来源" /><label for="review-note">审校说明（必填）</label><el-input id="review-note" v-model="form.review_note" placeholder="标签依据或拒绝原因" /><label class="learning-checkbox"><input v-model="form.redaction_confirmed" type="checkbox" />已确认不含姓名、联系方式、证件号等身份信息</label><label class="learning-checkbox"><input v-model="form.evidence_confirmed" type="checkbox" />已确认正负证据及来源，未将模型回答直接当作真值</label><div class="learning-actions"><el-button type="primary" native-type="submit" :disabled="!form.redaction_confirmed || !form.evidence_confirmed || !form.positive.trim() || !form.negative.trim() || !form.positive_source.trim() || !form.negative_source.trim() || !form.review_note.trim()" :loading="busy === 'approve'">审校通过</el-button><el-button :loading="busy === 'reject'" :disabled="!form.review_note.trim()" @click="review('reject')">拒绝此候选</el-button></div></fieldset></form><p v-if="!selected.consent" class="text-danger">用户已撤回授权，该候选不可用于训练。</p></template>
      </section></div>
      <section class="card"><div class="section-title"><div><h2>冻结批次与 BGE 训练准备</h2><p class="muted">按查询分组划分训练 / 验证集，保存去重指纹与来源清单。</p></div><RouterLink class="text-link" to="/training">查看训练记录 <AppIcon name="arrow" :size="14" /></RouterLink></div><EmptyState v-if="!batches.length" title="尚无训练批次" description="先完成证据审校，再选择通过的候选冻结批次。" compact />
        <template v-else><div class="learning-export-options"><label>导出格式<select v-model="exportFormat" aria-label="训练数据格式"><option value="triplets">同学脚本 · query/positive/negative</option><option value="flagembedding">FlagEmbedding · query/pos/neg</option></select></label><label>数据划分<select v-model="exportSplit" aria-label="导出数据划分"><option value="train">训练集</option><option value="validation">验证集</option></select></label></div><div class="learning-table-scroll"><table class="learning-table"><thead><tr><th>批次</th><th>样本 / 划分</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="batch in batches" :key="batch.id"><td><strong>{{ batch.label }}</strong><small>{{ formatDate(batch.created_at) }}</small><details><summary>数据指纹与清单</summary><code>{{ batch.sha256 }}</code><pre>{{ JSON.stringify(batch.manifest,null,2) }}</pre></details></td><td>{{ numberText(batch.sample_count) }} 条<small>训练 {{ numberText(batch.train_count) }} / 验证 {{ numberText(batch.validation_count) }}</small><small>{{ batch.holdout_status }}</small></td><td>{{ learningStatus(batch.status) }}</td><td><div class="learning-actions"><el-button size="small" :disabled="!!busy || batch.status === 'invalidated'" @click="download(batch)">下载 JSONL</el-button><el-button size="small" :disabled="!!busy || batch.status === 'invalidated'" @click="prepare(batch)">生成训练配置</el-button></div></td></tr></tbody></table></div></template>
      </section>
      <section v-if="prepared" class="card prepared-training"><div class="section-title"><div><h2>训练配置已准备</h2><p class="muted">{{ learningStatus(prepared.status) }} · 此步骤没有执行 GPU 训练</p></div><RouterLink :to="{path:'/training',query:{run:prepared.run_id}}" class="text-link">查看对应运行</RouterLink></div><p>{{ prepared.note }}</p><p class="learning-note break-word">配置文件：{{ prepared.config_path }}</p><pre v-if="commandLine">{{ commandLine }}</pre><el-button v-if="commandLine" size="small" @click="copyCommand">复制 PowerShell 命令</el-button><p class="learning-note">在现有 GPU 环境中显式执行命令后，同步真实训练日志，再导入评测结果。评测和人工确认通过后可登记活动版本；在线检索切换待同学接入。</p></section>
    </template>
  </div>
</template>
