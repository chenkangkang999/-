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
  it("sends training consent only after the user checks the optional authorization", async () => {
    const run={run_id:"run-opt-in",trace_id:"trace-opt-in",status:"succeeded",reply:{id:2,role:"assistant",content:"审核后回复"},steps:[]};
    vi.spyOn(http,"get").mockImplementation(async url=>({data:url==="/consultations/"?{results:[]}:url==="/consultations/1/runs/"?{results:[run]}:String(url).includes("/runs/")?run:{id:1,messages:[]}}));
    const post=vi.spyOn(http,"post").mockResolvedValue({data:{}}); const wrapper=await mountView();
    await wrapper.get('[aria-label="有帮助"]').trigger("click"); const consent=wrapper.get('[aria-label="允许脱敏反馈用于检索模型改进"]'); expect((consent.element as HTMLInputElement).checked).toBe(false);
    await consent.setValue(true); await wrapper.findAll("button").find(item=>item.text()==="提交反馈")!.trigger("click"); await flushPromises();
    expect(post).toHaveBeenCalledWith("/consultations/1/feedback/",expect.objectContaining({training_consent:true,rating:1})); expect(wrapper.text()).toContain("仍须脱敏与人工审校"); wrapper.unmount();
  });
  it("restores feedback consent after refresh and allows withdrawing it without removing the rating", async () => {
    const run = {run_id:"run-consented",trace_id:"trace-consented",status:"succeeded",reply:{id:2,role:"assistant",content:"经过审核的回复"},feedback:{id:4,rating:1,comment:"反馈原因",training_consent:true},steps:[]};
    vi.spyOn(http,"get").mockImplementation(async url=>({data:url==="/consultations/"?{results:[]}:url==="/consultations/1/runs/"?{results:[run]}:String(url).includes("/runs/")?run:{id:1,title:"合成测试",status:"active",messages:[]}}));
    const post=vi.spyOn(http,"post").mockResolvedValue({data:{training_consent:false}});
    const wrapper=await mountView();
    const revoke=wrapper.findAll("button").find(item=>item.text()==="撤回训练授权"); expect(revoke).toBeDefined(); await revoke!.trigger("click"); await flushPromises();
    expect(post).toHaveBeenCalledWith("/consultations/1/feedback/",{run_id:"run-consented",rating:1,comment:"反馈原因",training_consent:false});
    expect(wrapper.text()).toContain("未授权训练回流"); expect(wrapper.text()).not.toContain("撤回训练授权"); wrapper.unmount();
  });
  it("submits explicitly completed missing history and shows only recorded clinical stages", async () => {
    const run={run_id:"run-history",trace_id:"trace-history",status:"succeeded",reply:{id:2,role:"assistant",content:"请补充年龄"},steps:[],intake:{status:"awaiting_information",answers:{},missing_fields:["age"],questions:[{field:"age",label:"年龄",question:"你的年龄是多少？"}],summary:"病史尚未完整"},pipeline:{current_stage:"intake",reason:"病史尚未完整",stages:[{id:"precheck",label:"急症初筛",status:"completed"},{id:"intake",label:"多轮问诊",status:"waiting"},{id:"retrieval",label:"医学检索",status:"pending"}]}};
    vi.spyOn(http,"get").mockImplementation(async url=>({data:url==="/consultations/"?{results:[]}:url==="/consultations/1/runs/"?{results:[run]}:String(url).includes("/runs/")?run:{id:1,title:"合成病例",messages:[]}}));
    const post=vi.spyOn(http,"post").mockResolvedValue({data:{run_id:"new-run",trace_id:"new-trace",status:"pending",steps:[]}});
    const wrapper=await mountView();
    expect(wrapper.get('[aria-label="本次问诊进度"]').text()).toContain("未开始"); expect(wrapper.text()).toContain("补充病史，再进入后续评估");
    await wrapper.get("#intake-age").setValue("32"); await wrapper.get(".message-composer").trigger("submit"); await flushPromises();
    expect(post).toHaveBeenCalledWith("/consultations/1/runs/",expect.objectContaining({content:"年龄：32",intake:{age:"32"},client_request_id:expect.any(String)})); wrapper.unmount();
  });
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
      training_consent: false,
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
