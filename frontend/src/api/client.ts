import axios from "axios";

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: Number(import.meta.env.VITE_API_TIMEOUT_MS || 60000),
  withCredentials: true,
  withXSRFToken: true,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
  headers: { "Content-Type": "application/json" },
});

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public code?: string,
    public details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const body = error?.response?.data;
    const detail =
      body?.error?.message ||
      (typeof body?.error === "string" ? body.error : "") ||
      body?.message ||
      body?.detail ||
      body?.content?.[0];
    const fallback =
      error.code === "ECONNABORTED"
        ? "请求超时，请稍后刷新查看运行结果。"
        : error.response
          ? `请求失败（${error.response.status}），请稍后重试。`
          : "无法连接服务，请检查后端是否已启动。";
    return Promise.reject(
      new ApiError(
        typeof detail === "string" ? detail : fallback,
        error.response?.status,
        body?.error?.code || body?.code,
        body,
      ),
    );
  },
);

export function websocketUrl(consultationId: number): string {
  const configured = import.meta.env.VITE_WS_BASE_URL;
  const url = configured
    ? new URL(configured, window.location.origin)
    : new URL(http.defaults.baseURL || "/api/v1", window.location.origin);
  url.protocol =
    url.protocol === "https:" || url.protocol === "wss:" ? "wss:" : "ws:";
  url.pathname = `${configured ? url.pathname.replace(/\/$/, "") : ""}/ws/consultations/${consultationId}/`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

export function resultList<T>(
  data: T[] | { results?: T[]; items?: T[]; runs?: T[] },
): T[] {
  return Array.isArray(data)
    ? data
    : data.results || data.items || data.runs || [];
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "操作未完成，请重试。";
}
