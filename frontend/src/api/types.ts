export interface User {
  id: number;
  username: string;
  is_staff: boolean;
  email?: string;
  profile?: {
    display_name?: string;
    sex?: string;
    allergies?: string[];
  } | null;
}
export interface Citation {
  id?: string | number;
  title?: string;
  snippet?: string;
  source?: string;
  url?: string;
  source_url?: string;
  document_id?: string | number;
  chunk_id?: string | number;
}
export interface Message {
  id: number;
  role: string;
  content: string;
  agent_name?: string;
  citations?: Citation[];
  created_at?: string;
}
export interface Consultation {
  id: number;
  title: string;
  status: string;
  risk_level?: string;
  trace_id?: string;
  updated_at?: string;
  messages?: Message[];
}
export interface AgentStep {
  agent: string;
  status?: string;
  latency_ms?: number;
  error?: string | null;
  error_code?: string;
}
export interface Run {
  intake?: { status: "awaiting_information" | "ready" | "emergency"; answers: Record<string, unknown>; missing_fields: string[]; questions: Array<{ field: string; label: string; question: string }>; summary: string; extraction_status?: string };
  pipeline?: { stages: Array<{ id: string; label: string; status: string; agents?: string[]; reason?: string }>; current_stage?: string; reason?: string; updated_at?: string };
  feedback?: { id: number; rating: number; comment?: string; training_consent: boolean } | null;
  run_id: string;
  trace_id: string;
  status: string;
  error?: string | { message?: string; code?: string } | null;
  reply?: Message | null;
  message?: Message;
  steps?: AgentStep[];
  soap?: Record<string, unknown> | string | null;
  plain_explanation?: string | null;
  guidance?: unknown;
  safety?: Record<string, unknown> | null;
  metadata?: { safety?: Record<string, unknown> | null; intake?: Run["intake"]; pipeline?: Run["pipeline"] };
  created_at?: string;
}
export interface AgentInfo {
  name: string;
  description?: string;
  label?: string;
  enabled?: boolean;
}
export const agentLabels: Record<string, string> = {
  triage: "问诊",
  retrieval: "医学检索",
  risk: "风险评估",
  medication: "用药审核",
  debate: "诊断辩论",
  debate_agent: "诊断辩论",
  explainer: "白话解释",
  safety: "安全护栏",
  coordinator: "协调器",
};
export const agentLabel = (name: string) => agentLabels[name] || name;
export const isRunActive = (status?: string) =>
  !!status && ["queued", "pending", "running", "started"].includes(status);
export const statusLabel = (status?: string) =>
  ({
    queued: "等待中",
    pending: "等待中",
    running: "进行中",
    started: "进行中",
    succeeded: "已完成",
    completed: "已完成",
    failed: "失败",
    blocked: "已拦截",
    skipped: "已跳过",
    cancelled: "已取消",
  })[status || ""] ||
  status ||
  "待运行";
export const formatDate = (value?: string) =>
  value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
export const safeSourceUrl = (value?: string) => {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
};
