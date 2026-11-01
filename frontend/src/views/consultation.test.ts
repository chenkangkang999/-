import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import { http, ApiError } from "@/api/client";
import ConsultationView from "./ConsultationView.vue";

class TestSocket {
  static instances: TestSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(public url: string) {
    TestSocket.instances.push(this);
  }
  close() {}
  emit(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) });
  }
}
beforeEach(() => {
  TestSocket.instances = [];
  vi.stubGlobal("WebSocket", TestSocket);
  HTMLElement.prototype.scrollTo = vi.fn();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/consultation/:id?", component: ConsultationView }],
  });
  await router.push("/consultation/1");
  await router.isReady();
  const wrapper = mount(ConsultationView, {
    global: { plugins: [router, ElementPlus] },
  });
  await flushPromises();
  return wrapper;
}
describe("asynchronous consultation", () => {
  it("restores a run, consumes real completion events and submits feedback to its run", async () => {
    let completed = false;
    const userMessage = { id: 10, role: "user", content: "咳嗽三天" };
    const answer = {
      id: 11,
      role: "assistant",
      content: "请记录症状变化。",
      citations: [{ title: "指南证据", source: "doc-1" }],
    };
    vi.spyOn(http, "get").mockImplementation(async (url) => {
      if (url === "/consultations/")
        return {
          data: { results: [{ id: 1, title: "咳嗽", status: "active" }] },
        };
      if (url === "/consultations/1/")
        return {
          data: {
            id: 1,
            title: "咳嗽",
            status: "active",
            messages: completed ? [userMessage, answer] : [userMessage],
          },
        };
      if (url === "/consultations/1/runs/")
        return {
          data: [
            {
              run_id: "run-1",
              trace_id: "trace-1",
              status: "running",
              steps: [{ agent: "safety", status: "running" }],
            },
          ],
        };
      return {
        data: {
          run_id: "run-1",
          trace_id: "trace-1",
          status: completed ? "completed" : "running",
          steps: [
            { agent: "safety", status: completed ? "succeeded" : "running" },
          ],
          reply: completed ? answer : null,
          soap: completed ? { subjective: "咳嗽三天" } : null,
        },
      };
    });
    const post = vi
      .spyOn(http, "post")
      .mockResolvedValue({ data: { saved: true } });
    const wrapper = await mountView();
    expect(wrapper.text()).toContain("咳嗽三天");
    expect(wrapper.text()).toContain("智能体正在协作");
    completed = true;
    TestSocket.instances[0].emit({
      type: "run.completed",
      run_id: "run-1",
      trace_id: "trace-1",
      payload: {},
    });
    await flushPromises();
    expect(wrapper.text()).toContain("请记录症状变化。");
    expect(wrapper.text()).toContain("主观症状");
    await wrapper.get('[aria-label="有帮助"]').trigger("click");
    const submit = wrapper
      .findAll("button")
      .find((button) => button.text() === "提交反馈");
    await submit!.trigger("click");
    await flushPromises();
    expect(post).toHaveBeenCalledWith("/consultations/1/feedback/", {
      run_id: "run-1",
      rating: 1,
      comment: "",
    });
    expect(wrapper.text()).toContain("反馈已保存");
    wrapper.unmount();
  });
  it("retains a request id on a retry after an uncertain network failure", async () => {
    vi.spyOn(http, "get").mockImplementation(async (url) => ({
      data:
        url === "/consultations/"
          ? { results: [{ id: 1, title: "会话" }] }
          : url === "/consultations/1/runs/"
            ? []
            : { id: 1, title: "会话", status: "active", messages: [] },
    }));
    const post = vi
      .spyOn(http, "post")
      .mockRejectedValue(new ApiError("连接中断，请重试"));
    const wrapper = await mountView();
    await wrapper.get("textarea").setValue("咳嗽三天");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);
    expect(post.mock.calls[0][1]).toMatchObject({
      content: "咳嗽三天",
      client_request_id: expect.any(String),
    });
    expect(wrapper.get("textarea").element.value).toBe("咳嗽三天");
    wrapper.unmount();
  });
});
