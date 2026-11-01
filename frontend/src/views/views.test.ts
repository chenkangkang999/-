import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import { http, ApiError } from "@/api/client";
import { useSessionStore } from "@/stores/session";
import LoginView from "./LoginView.vue";
import AgentsView from "./AgentsView.vue";
import BillingView from "./BillingView.vue";

afterEach(() => vi.restoreAllMocks());
async function context() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div />" } },
      { path: "/login", component: LoginView },
      { path: "/agents/:name?", component: AgentsView },
      { path: "/consultation/:id?", component: { template: "<div />" } },
    ],
  });
  await router.push("/login");
  await router.isReady();
  return { pinia, router, global: { plugins: [pinia, router, ElementPlus] } };
}
describe("login", () => {
  it("obtains CSRF before sending credentials and stores the authenticated user", async () => {
    const get = vi.spyOn(http, "get").mockResolvedValue({ data: {} });
    const post = vi.spyOn(http, "post").mockResolvedValue({
      data: { id: 5, username: "member", is_staff: false },
    });
    const ctx = await context();
    const wrapper = mount(LoginView, { global: ctx.global });
    await flushPromises();
    await wrapper.get("#username").setValue("member");
    await wrapper.get("#password").setValue("test-password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(get).toHaveBeenCalledWith("/accounts/csrf/");
    expect(post).toHaveBeenCalledWith("/accounts/login/", {
      username: "member",
      password: "test-password",
    });
    expect(get.mock.invocationCallOrder[0]).toBeLessThan(
      post.mock.invocationCallOrder[0],
    );
    expect(useSessionStore().user?.username).toBe("member");
    wrapper.unmount();
  });
  it("shows backend authentication failures without marking the session logged in", async () => {
    vi.spyOn(http, "get").mockResolvedValue({ data: {} });
    vi.spyOn(http, "post").mockRejectedValue(
      new ApiError("账号或密码错误", 400),
    );
    const ctx = await context();
    const wrapper = mount(LoginView, { global: ctx.global });
    await flushPromises();
    await wrapper.get("#username").setValue("member");
    await wrapper.get("#password").setValue("wrong");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("账号或密码错误");
    expect(useSessionStore().user).toBeNull();
    wrapper.unmount();
  });
});
describe("protected Agent testing", () => {
  it("hides testing controls from non-staff accounts", async () => {
    vi.spyOn(http, "get").mockImplementation(async (url) => ({
      data:
        url === "/agents/"
          ? {
              agents: [{ name: "safety", description: "安全审核" }],
              debate_enabled: true,
            }
          : { results: [] },
    }));
    const post = vi.spyOn(http, "post");
    const ctx = await context();
    useSessionStore().user = { id: 1, username: "member", is_staff: false };
    const wrapper = mount(AgentsView, { global: ctx.global });
    await flushPromises();
    expect(wrapper.text()).toContain("独立测试仅对项目管理员开放");
    expect(wrapper.find("#agent-test-content").exists()).toBe(false);
    expect(post).not.toHaveBeenCalled();
    wrapper.unmount();
  });
  it("shows provider errors from an actual test request", async () => {
    vi.spyOn(http, "get").mockImplementation(async (url) => ({
      data:
        url === "/agents/"
          ? { agents: [{ name: "explainer" }] }
          : { results: [] },
    }));
    const post = vi.spyOn(http, "post").mockRejectedValue(
      new ApiError("LLM API Key 未配置", 503, "provider_unavailable", {
        status: "failed",
        trace_id: "failed-trace-001",
        steps: [],
      }),
    );
    const ctx = await context();
    useSessionStore().user = { id: 1, username: "admin", is_staff: true };
    const wrapper = mount(AgentsView, { global: ctx.global });
    await flushPromises();
    await wrapper.get("#agent-test-content").setValue("测试上下文");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(post).toHaveBeenCalledWith("/agents/explainer/test/", {
      content: "测试上下文",
    });
    expect(wrapper.text()).toContain("LLM API Key 未配置");
    expect(wrapper.text()).toContain("failed-trace-001");
    wrapper.unmount();
  });
});
describe("billing empty state", () => {
  it("marks missing pricing and avoids invented bills", async () => {
    vi.spyOn(http, "get").mockImplementation(async (url) => ({
      data:
        url === "/billing/usage/"
          ? {
              today: { cost: "0", tokens: 0 },
              total: { cost: "0", tokens: 0 },
              records: 0,
              latest: [],
              by_day: [],
            }
          : { configured: false, price_configured: false },
    }));
    const ctx = await context();
    const wrapper = mount(BillingView, { global: ctx.global });
    await flushPromises();
    expect(wrapper.text()).toContain("模型价格尚未配置");
    expect(wrapper.text()).toContain("暂无调用流水");
    expect(wrapper.text()).toContain("预算尚未启用");
    wrapper.unmount();
  });
});

describe("per-query billing", () => {
  it("keeps two runs in one consultation separate and links to the exact run", async () => {
    const firstRun = "11111111-1111-4111-8111-111111111111";
    const secondRun = "22222222-2222-4222-8222-222222222222";
    vi.spyOn(http, "get").mockImplementation(async (url) => ({
      data:
        url === "/billing/usage/"
          ? {
              currency: "CNY",
              today: { cost: "0.30", tokens: 300 },
              total: { cost: "0.30", tokens: 300 },
              records: 3,
              by_run: [
                {
                  run_id: firstRun,
                  consultation_id: 8,
                  tokens: 100,
                  cost: "0.10",
                },
                {
                  run_id: secondRun,
                  consultation_id: 8,
                  tokens: 200,
                  cost: "0.20",
                },
              ],
              by_query: [{ consultation_id: 8, tokens: 300, cost: "0.30" }],
              latest: [
                {
                  id: 1,
                  run_id: firstRun,
                  agent: "safety",
                  model: "configured-model",
                  tokens_in: 50,
                  tokens_out: 50,
                  cost: "0.10",
                  measurement: "provider",
                },
              ],
            }
          : { configured: true, price_configured: true },
    }));
    const ctx = await context();
    const wrapper = mount(BillingView, { global: ctx.global });
    await flushPromises();
    const table = wrapper.get(".single-run-billing-table");
    expect(table.findAll(".el-table__body-wrapper tbody tr")).toHaveLength(2);
    expect(table.text()).toContain("0.10");
    expect(table.text()).toContain("0.20");
    expect(table.get(`code[title="${firstRun}"]`).text()).toContain("11111111");
    expect(table.get(`code[title="${secondRun}"]`).text()).toContain(
      "22222222",
    );
    expect(table.findAll("a").map((link) => link.attributes("href"))).toEqual([
      `/consultation/8?run=${firstRun}`,
      `/consultation/8?run=${secondRun}`,
    ]);
    expect(wrapper.findAll(`code[title="${firstRun}"]`)).toHaveLength(2);
    expect(wrapper.text()).toContain("按问诊汇总");
    wrapper.unmount();
  });
});
