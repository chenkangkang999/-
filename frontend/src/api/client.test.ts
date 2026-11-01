import { afterEach, describe, expect, it, vi } from "vitest";
import { http, resultList, websocketUrl, ApiError } from "./client";
import { isRunActive, safeSourceUrl } from "./types";

afterEach(() => {
  vi.unstubAllEnvs();
});
describe("API configuration and helpers", () => {
  it("uses Django CSRF names and credentialed requests", () => {
    expect(http.defaults.xsrfCookieName).toBe("csrftoken");
    expect(http.defaults.xsrfHeaderName).toBe("X-CSRFToken");
    expect(http.defaults.withCredentials).toBe(true);
  });
  it("supports paginated and unpaginated real API data", () => {
    expect(resultList({ results: [{ id: 1 }] })).toEqual([{ id: 1 }]);
    expect(resultList({ runs: [{ run_id: "abc" }] })).toEqual([
      { run_id: "abc" },
    ]);
    expect(resultList([])).toEqual([]);
  });
  it("derives secure websocket URLs from a configured endpoint", () => {
    vi.stubEnv("VITE_WS_BASE_URL", "https://backend.example.org");
    expect(websocketUrl(23)).toBe(
      "wss://backend.example.org/ws/consultations/23/",
    );
  });
  it("distinguishes terminal failed runs from active tasks", () => {
    expect(isRunActive("queued")).toBe(true);
    expect(isRunActive("running")).toBe(true);
    expect(isRunActive("failed")).toBe(false);
    expect(isRunActive("completed")).toBe(false);
    expect(safeSourceUrl("data:text/html,hello")).toBeUndefined();
  });
  it("retains status and readable errors for the UI", () => {
    const error = new ApiError("模型尚未配置", 503, "provider_unavailable");
    expect(error.status).toBe(503);
    expect(error.message).toBe("模型尚未配置");
  });
});
