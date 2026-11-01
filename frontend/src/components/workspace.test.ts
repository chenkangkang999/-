import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import ElementPlus from "element-plus";
import WorkspaceNavigation from "./WorkspaceNavigation.vue";
import PageScene from "./PageScene.vue";
import HomeView from "@/views/HomeView.vue";
import { workspaceBackgroundStyle, pageDefinition } from "@/config/workspace";
import { http } from "@/api/client";
import { useSessionStore } from "@/stores/session";

vi.mock("@/components/MetricChart.vue", () => ({ default: {
  name: "MetricChart", props: ["labels", "values", "unit"],
  template: '<div data-testid="actual-chart">{{ JSON.stringify(labels) }}|{{ JSON.stringify(values) }}</div>',
} }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });
async function context() {
  const pinia = createPinia(); setActivePinia(pinia);
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/", component: { template: "<div />" } },
    { path: "/consultation/:id?", component: { template: "<div />" } },
    { path: "/agents/:name?", component: { template: "<div />" } },
    { path: "/monitoring", component: { template: "<div />" } },
    { path: "/billing", component: { template: "<div />" } },
  ] });
  await router.push("/agents"); await router.isReady();
  useSessionStore().user = { id: 1, username: "member", is_staff: false };
  return { plugins: [pinia, router, ElementPlus] };
}
describe("workspace navigation and scenes", () => {
  it("provides the five primary destinations and identifies the current page", async () => {
    const wrapper = mount(WorkspaceNavigation, { props: { activePage: "agents" }, global: await context() });
    const links = wrapper.findAll("a");
    expect(links.map(link => link.attributes("href"))).toEqual(["/", "/consultation", "/agents", "/monitoring", "/billing"]);
    expect(wrapper.get('[aria-current="page"]').text()).toBe("智能体中心");
    expect(wrapper.findAll('[aria-current="page"]')).toHaveLength(1);
    wrapper.unmount();
  });
  it("selects a distinct medical scene for each functional page", () => {
    const consultation = mount(PageScene, { props: { page: pageDefinition("consultation") } });
    const billing = mount(PageScene, { props: { page: pageDefinition("billing") } });
    expect(consultation.get("h1").text()).toContain("健康问题");
    expect(billing.get("h1").text()).toContain("费用有依据");
    expect(consultation.get("svg").attributes("data-scene")).toBe("consultation");
    expect(billing.get("svg").attributes("data-scene")).toBe("billing");
    expect(billing.text()).not.toContain("已连接");
    consultation.unmount(); billing.unmount();
  });
  it("supports a configurable public background with the bundled WebP as its default", () => {
    vi.stubEnv("VITE_WORKSPACE_BACKGROUND_URL", "");
    expect(workspaceBackgroundStyle()["--workspace-background-image"]).toBe('url("/images/medical-atmosphere-v2.webp")');
    vi.stubEnv("VITE_WORKSPACE_BACKGROUND_URL", "/custom/clinic.webp");
    expect(workspaceBackgroundStyle()["--workspace-background-image"]).toBe('url("/custom/clinic.webp")');
  });
});
describe("home factual status", () => {
  it("keeps unavailable services and missing medical metrics visibly unavailable", async () => {
    vi.spyOn(http, "get").mockImplementation(async url => ({ data:
      url === "/monitoring/overview/" ? { agents: { total: 0, failed: 0 }, latency_ms: { avg: null }, knowledge: { status: "not_connected", documents: null }, feedback: { count: 0, positive: 0, negative: 0, positive_rate: null }, by_agent: [] }
      : url === "/agents/" ? { agents: [], llm_configured: false } : { results: [] },
    }));
    const wrapper = mount(HomeView, { global: await context() }); await flushPromises();
    expect(wrapper.text()).toContain("未配置"); expect(wrapper.text()).toContain("未接入");
    expect(wrapper.findAll(".stat-card")[2].text()).toContain("—");
    expect(wrapper.text()).toContain("尚无调用记录");
    expect(wrapper.text()).toContain("流程示意");
    expect(wrapper.text()).not.toContain("已连接");
    expect(wrapper.find('[data-testid="actual-chart"]').exists()).toBe(false);
    wrapper.unmount();
  });
  it("plots the real returned agent counts rather than decorative sample values", async () => {
    vi.spyOn(http, "get").mockImplementation(async url => ({ data:
      url === "/monitoring/overview/" ? { scope: "own", agents: { total: 13, failed: 1 }, knowledge: { status: "not_connected", documents: null }, by_agent: [{ agent: "triage", total: 8 }, { agent: "safety", total: 5 }] }
      : url === "/agents/" ? { agents: [{ name: "triage" }, { name: "safety" }], llm_configured: true } : { results: [] },
    }));
    const wrapper = mount(HomeView, { global: await context() }); await flushPromises();
    expect(wrapper.get('[data-testid="actual-chart"]').text()).toContain("[8,5]");
    expect(wrapper.text()).toContain("已配置");
    expect(wrapper.text()).toContain("流程示意");
    wrapper.unmount();
  });
});
