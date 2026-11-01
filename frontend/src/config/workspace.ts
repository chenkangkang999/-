import type { CSSProperties } from "vue";

export type WorkspacePage = "home" | "consultation" | "agents" | "monitoring" | "billing";
export interface PageDefinition {
  name: WorkspacePage;
  label: string;
  title: string;
  description: string;
  to: string;
  icon: string;
  tags: string[];
  scenePosition: string;
}

export const workspacePages: PageDefinition[] = [
  { name: "home", label: "工作台概览", title: "工作台概览", description: "多智能体协作，让健康信息更清晰。", to: "/", icon: "home", tags: ["协作问诊", "循证参考", "安全审核"], scenePosition: "center 40%" },
  { name: "consultation", label: "协作问诊", title: "把你的健康问题，认真说清楚", description: "记录症状与变化，查看协作过程、医学证据和就医指引。", to: "/consultation", icon: "chat", tags: ["会话记录", "证据追踪", "安全审核"], scenePosition: "center 50%" },
  { name: "agents", label: "智能体中心", title: "各有所长，共同完成一次协作", description: "了解专职智能体，查看真实运行记录与独立测试结果。", to: "/agents", icon: "agents", tags: ["能力分工", "独立测试", "调用记录"], scenePosition: "65% 35%" },
  { name: "monitoring", label: "运行监控", title: "每次调用，都看得见", description: "检索性能、反馈质量和运行状态，来自真实业务记录。", to: "/monitoring", icon: "chart", tags: ["性能分析", "质量反馈", "服务状态"], scenePosition: "30% 45%" },
  { name: "billing", label: "用量与账单", title: "用量有记录，费用有依据", description: "按运行查看模型费用，核对输入输出用量与每日预算。", to: "/billing", icon: "bill", tags: ["逐次账单", "用量溯源", "预算管理"], scenePosition: "70% 55%" },
];

export function pageDefinition(name: unknown): PageDefinition {
  return workspacePages.find(page => page.name === name) || workspacePages[0];
}

export function workspaceBackgroundStyle(imageUrl = import.meta.env.VITE_WORKSPACE_BACKGROUND_URL || "/images/medical-atmosphere-v2.webp"): CSSProperties {
  return { "--workspace-background-image": `url(${JSON.stringify(imageUrl)})` } as CSSProperties;
}

export const collaborationFlow = [
  { id: "triage", title: "问诊", icon: "chat", description: "整理症状与主诉", agents: [{ name: "triage", label: "问诊" }] },
  { id: "retrieval", title: "医学检索", icon: "book", description: "查找可追溯证据", agents: [{ name: "retrieval", label: "医学检索" }] },
  { id: "assessment", title: "并行评估", icon: "pulse", description: "风险与用药分别评估", agents: [{ name: "risk", label: "风险" }, { name: "medication", label: "用药" }] },
  { id: "debate", title: "诊断辩论", icon: "agents", description: "存在分歧时质证仲裁", agents: [{ name: "debate", label: "诊断辩论" }] },
  { id: "explainer", title: "白话解释", icon: "chat", description: "形成小结与就医指引", agents: [{ name: "explainer", label: "白话解释" }] },
  { id: "safety", title: "安全护栏", icon: "shield", description: "审核最终回复再发布", agents: [{ name: "safety", label: "安全护栏" }] },
];
