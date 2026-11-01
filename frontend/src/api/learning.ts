export interface DataAsset {
  id: number; key: string; title: string; source: string; path: string; format: string;
  reported_rows: number | null; observed_rows: number | null; file_status: string;
  bytes: number | null; sha256?: string; provenance: string;
}
export interface PipelineStage { id: string; label: string; status: string; reason?: string; agents?: string[] }
export interface TrainingRun {
  id: string; label: string; status: string; phase: string; current_step: number | null;
  total_steps: number | null; progress: number | null; epoch: number | null;
  metrics: Record<string, number>; config: Record<string, unknown>; source: string;
  updated_at?: string; pipeline: PipelineStage[]; provenance?: { kind?: string; stop_reason?: string; note?: string };
}
export interface TrainingEvent {
  id: number; kind: string; phase: string; level: string; message: string;
  step: number | null; metrics: Record<string, number>; created_at?: string;
}
export interface Evaluation {
  id: string; title: string; source: string; verified: boolean;
  scope: { kind: string; queries?: number; candidates?: number; positive?: number; negative?: number; note?: string };
  metrics: Array<{ metric: string; base: number; baseline: number; cosine: number }>;
  selected_model: string; sha256?: string;
}
export interface LearningOverview {
  configuration: Record<string, Record<string, unknown>>;
  selected_profile: { id: string; label: string; parameters: Record<string, unknown>; source: string };
  datasets: { total: number; verified: number; missing: number };
  training: { runs: number; active: number; last_run?: TrainingRun | null }; updated_at?: string;
}
export interface FlywheelOverview {
  feedback_total: number; consented: number; pending: number; approved: number; rejected: number;
  revoked: number; batches: number; training_requests: number;
  policy: { requires_consent: boolean; requires_review: boolean; automatic_training: boolean };
}
export interface FeedbackCandidate {
  id: number; feedback_id: number; run_id: string; rating: number; status: string; query: string;
  comment: string; citations: Array<Record<string, unknown>>; positive: string; negative: string;
  positive_source: string; negative_source: string; review_note: string; consent: boolean;
  redacted: boolean; query_hash: string; updated_at?: string;
}
export interface TrainingBatch {
  id: string; label: string; status: string; sample_count: number; train_count: number;
  validation_count: number; sha256: string; holdout_status: string; manifest: Record<string, unknown>;
  created_at?: string;
}
export interface PreparedTraining {
  batch_id: string; run_id: string; status: string; command: string[]; config_path: string;
  training_enabled: boolean; note: string;
}
export const learningStatus = (status?: string) => ({
  ready: "待启动", unknown: "状态待核验", running: "训练中", completed: "已完成", failed: "失败",
  early_stopped: "已提前停止", not_started: "未开始", interrupted: "已中断", pending: "待审校", approved: "已通过", rejected: "已拒绝", revoked: "已撤回",
  missing: "未找到文件", verified: "已核验", error: "核验失败", skipped: "已跳过",
  waiting: "等待补充", invalidated: "已失效", frozen: "已冻结", exported: "已导出",
})[status || ""] || status || "未接入";
export const numberText = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("zh-CN") : "—";
export const configText = (value: unknown) => value == null ? "—" : typeof value === "object" ? JSON.stringify(value) : typeof value === "boolean" ? value ? "开启" : "关闭" : String(value);
