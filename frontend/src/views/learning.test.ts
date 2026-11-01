import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import { http, ApiError } from "@/api/client";
import { useSessionStore } from "@/stores/session";
import TrainingView from "./TrainingView.vue";
import FlywheelView from "./FlywheelView.vue";
import AgentsView from "./AgentsView.vue";
vi.mock("@/components/TrainingCurve.vue", () => ({ default: { props: ["series"], template: '<div data-testid="training-curve">{{JSON.stringify(series)}}</div>' } }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function context(path = "/training", staff = true) {
  const pinia = createPinia(); setActivePinia(pinia);
  const router = createRouter({ history: createMemoryHistory(), routes: [
    {path:"/training",component:TrainingView}, {path:"/flywheel",component:FlywheelView}, {path:"/agents/:name?",component:AgentsView},
  ] }); await router.push(path); await router.isReady();
  useSessionStore().user = {id:1,username:"reviewer",is_staff:staff};
  return {plugins:[pinia,router,ElementPlus]};
}
const overview = {configuration:{model:{model_id:"configured-embedding-model"}, train:{num_epochs:3}},selected_profile:{id:"selected",label:"配置中的选型",parameters:{num_epochs:3,learning_rate:0.001}},datasets:{total:1,verified:0,missing:1},training:{runs:0,active:0}};
function trainingGet(extra: Record<string,unknown> = {}) {
  return vi.spyOn(http,"get").mockImplementation(async url => ({ data: extra[String(url)] ?? (url === "/learning/overview/" ? overview : {results:[]}) }));
}
const candidate = {id:"candidate-1",feedback_id:1,run_id:"run-1",rating:-1,status:"pending",query:"咳嗽多久需要就诊",comment:"证据不对应",citations:[],positive:"",negative:"",positive_source:"",negative_source:"",review_note:"",consent:true,redacted:true,query_hash:"query-hash"};
const batch = {id:"batch-1",label:"已审校批次",status:"frozen",sample_count:2,train_count:1,validation_count:1,sha256:"batch-hash",holdout_status:"verified",manifest:{groups:2}};
function flywheelGet(extra: Record<string,unknown> = {}) {
  return vi.spyOn(http,"get").mockImplementation(async url => ({data: extra[String(url)] ?? (url === "/learning/flywheel/overview/" ? {feedback_total:3,consented:1,pending:1,approved:0,revoked:0,rejected:0,batches:0,training_requests:0} : {results:[]})}));
}
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll("button").find(item => item.text().includes(text))!;

describe("training evidence", () => {
  it("does not request staff data from ordinary accounts",async () => {
    const get=vi.spyOn(http,"get"); const wrapper=mount(TrainingView,{global:await context("/training",false)}); await flushPromises();
    expect(wrapper.text()).toContain("仅对项目管理员开放"); expect(get).not.toHaveBeenCalled(); wrapper.unmount();
  });
  it("separates document reports from verified files and never invents a running log",async () => {
    trainingGet({"/learning/datasets/":{results:[{id:"dataset",key:"train",title:"医疗检索训练集",source:"提供的技术文档",format:"jsonl",reported_rows:123,observed_rows:null,file_status:"missing",path:"configured/train.jsonl"}]},
      "/learning/evaluations/":{results:[{id:"report",title:"文档对比实验",verified:false,source:"document_reported",scope:{kind:"candidate_pool",queries:6,positive:1,negative:3},metrics:[{metric:"Recall@1",base:0.3,baseline:0.4,cosine:0.35}],selected_model:"baseline"}]}});
    const wrapper=mount(TrainingView,{global:await context()}); await flushPromises();
    expect(wrapper.text()).toContain("123"); expect(wrapper.text()).toContain("未找到文件"); expect(wrapper.text()).toContain("尚无训练日志");
    expect(wrapper.text()).toContain("文档报告 · 尚未核验原始产物"); expect(wrapper.text()).toContain("不能等同 Milvus 全库召回率");
    expect(wrapper.text()).toContain("configured-embedding-model"); expect(wrapper.text()).not.toContain("100%"); expect(button(wrapper,"查看样例").attributes("disabled")).toBeDefined(); wrapper.unmount();
  });
  it("requests only bounded, redacted examples for a verified dataset",async () => {
    const get=trainingGet({"/learning/datasets/":{results:[{id:1,key:"cmedqa-train",title:"医疗检索训练集",format:"jsonl",file_status:"verified",source:"已导入文件",path:"allowed/train.jsonl",reported_rows:4,observed_rows:4}]},"/learning/datasets/cmedqa-train/preview/":{asset_key:"cmedqa-train",fields:["query","positive","negative"],results:[{query:"联系***，询问合成症状",positive:"相关证据",negative:"不相关证据"}],sampled_rows:1,note:"已脱敏"}});
    const wrapper=mount(TrainingView,{global:await context()}); await flushPromises(); await button(wrapper,"查看样例").trigger("click"); await flushPromises();
    expect(get).toHaveBeenCalledWith("/learning/datasets/cmedqa-train/preview/",{params:{limit:3}}); const panel=wrapper.get('[aria-label="脱敏数据样例"]'); expect(panel.text()).toContain("查询问题"); expect(panel.text()).toContain("联系***"); expect(panel.text()).toContain("仍需人工复核");
    await button(wrapper,"收起样例").trigger("click"); expect(wrapper.find('[aria-label="脱敏数据样例"]').exists()).toBe(false); wrapper.unmount();
  });
  it("surfaces preview failures instead of filling sample records",async () => {
    const get=trainingGet({"/learning/datasets/":{results:[{id:1,key:"changed",title:"已变更数据",file_status:"verified",format:"csv"}]}});
    const previous=get.getMockImplementation()!; get.mockImplementation(async (...args)=> {if(String(args[0]).includes("/preview/")) throw new ApiError("文件已变化，请重新核验",409); return previous(...args);});
    const wrapper=mount(TrainingView,{global:await context()}); await flushPromises(); await button(wrapper,"查看样例").trigger("click"); await flushPromises(); expect(wrapper.text()).toContain("文件已变化，请重新核验"); expect(wrapper.findAll(".asset-preview-record")).toHaveLength(0); wrapper.unmount();
  });
  it("uses durable run records, cursors and actual metric events",async () => {
    const run={id:"training-1",label:"导入的真实运行",status:"unknown",source:"trainer_state",current_step:4,total_steps:10,progress:null,epoch:0.4,metrics:{loss:0.7},config:{},pipeline:[{id:"train",label:"模型训练",status:"running"}]};
    const get=trainingGet({"/learning/runs/":{results:[run]},"/learning/runs/training-1/":run,"/learning/runs/training-1/events/":{results:[{id:7,kind:"metric",phase:"train",level:"info",message:"实际记录",step:4,metrics:{loss:0.7}}],next_cursor:7}});
    const wrapper=mount(TrainingView,{global:await context()}); await flushPromises();
    expect(wrapper.text()).toContain("不估造百分比"); expect(wrapper.get('[data-testid="training-curve"]').text()).toContain("[4,0.7]");
    await button(wrapper,"刷新").trigger("click"); await flushPromises();
    expect(get).toHaveBeenCalledWith("/learning/runs/training-1/events/",{params:{after:7}}); expect(wrapper.findAll(".training-log li")).toHaveLength(1); wrapper.unmount();
  });
  it("shows sync and configuration failures without claiming a GPU run started",async () => {
    trainingGet(); const post=vi.spyOn(http,"post").mockRejectedValue(new ApiError("产物目录未接入",400));
    const wrapper=mount(TrainingView,{global:await context()}); await flushPromises(); await button(wrapper,"同步本机产物").trigger("click"); await flushPromises();
    expect(wrapper.text()).toContain("产物目录未接入"); expect(post).toHaveBeenCalledWith("/learning/sync/",{}); expect(wrapper.text()).toContain("尚无训练日志"); wrapper.unmount();
  });
  it("keeps early-stopped history separate from the selected configuration",async () => {
    const run={id:"stopped",label:"余弦历史运行",status:"early_stopped",source:"trainer_state",current_step:12,total_steps:25,progress:48,config:{train:{lr_scheduler_type:"cosine"}},pipeline:[{id:"training",label:"LoRA微调",status:"early_stopped"}]};
    trainingGet({"/learning/runs/":{results:[run]},"/learning/runs/stopped/":run,"/learning/runs/stopped/events/":{results:[],next_cursor:0}});
    const wrapper=mount(TrainingView,{global:await context()}); await flushPromises();
    expect(wrapper.text()).toContain("已提前停止"); expect(wrapper.text()).toContain("48.0%"); expect(wrapper.text()).toContain("不能当作当前选型配置的训练日志"); expect(wrapper.text()).toContain('"lr_scheduler_type": "cosine"'); wrapper.unmount();
  });
  it("requires a review note and explicit confirmation before model activation",async () => {
    const post=vi.spyOn(http,"post").mockResolvedValue({data:{}});
    trainingGet({"/learning/models/":{results:[{id:"model-1",label:"经过评测的模型",run_id:"run-1",adapter_path:"allowed/adapter",sha256:"model-hash",is_active:false,validation_status:"evaluated"}],activations:[],active_id:null}});
    const wrapper=mount(TrainingView,{global:await context()}); await flushPromises();
    expect(button(wrapper,"登记为活动版本").attributes("disabled")).toBeDefined(); expect(wrapper.text()).toContain("版本不匹配会阻断向量检索");
    await wrapper.get('[aria-label="模型版本审校说明"]').setValue("已核对同测试集评测产物"); await wrapper.get('.model-review input[type="checkbox"]').setValue(true);
    await button(wrapper,"登记为活动版本").trigger("click"); await flushPromises();
    expect(post).toHaveBeenCalledWith("/learning/models/model-1/activate/",{review_note:"已核对同测试集评测产物",evidence_confirmed:true}); wrapper.unmount();
  });
  it("can roll the first model activation back to the base without inventing a previous adapter",async () => {
    const post=vi.spyOn(http,"post").mockResolvedValue({data:{}});
    trainingGet({"/learning/models/":{results:[{id:"model-1",label:"已启用模型",is_active:true,validation_status:"evaluated",sha256:"hash"}],activations:[{id:12,version_id:"model-1",previous_id:null,review_note:"首次启用"}],active_id:"model-1"}});
    const wrapper=mount(TrainingView,{global:await context()}); await flushPromises(); await wrapper.get('[aria-label="模型版本审校说明"]').setValue("恢复基座对照"); await button(wrapper,"撤回活动登记").trigger("click"); await flushPromises();
    expect(post).toHaveBeenCalledWith("/learning/models/rollback/",{activation_id:12,review_note:"恢复基座对照"}); wrapper.unmount();
  });
});

describe("feedback curation", () => {
  it("keeps ordinary users outside the staff feedback corpus",async () => {
    const get=vi.spyOn(http,"get"); const wrapper=mount(FlywheelView,{global:await context("/flywheel",false)}); await flushPromises();
    expect(wrapper.text()).toContain("仅对项目管理员开放"); expect(get).not.toHaveBeenCalled(); wrapper.unmount();
  });
  it("requires explicit evidence and redaction review rather than treating a dislike as a negative label",async () => {
    flywheelGet({"/learning/flywheel/candidates/":{results:[candidate]}}); const post=vi.spyOn(http,"post").mockResolvedValue({data:{}});
    const wrapper=mount(FlywheelView,{global:await context("/flywheel")}); await flushPromises(); await button(wrapper,candidate.query).trigger("click");
    expect(button(wrapper,"审校通过").attributes("disabled")).toBeDefined(); expect((wrapper.get("#negative-evidence").element as HTMLTextAreaElement).value).toBe("");
    await wrapper.get("#positive-evidence").setValue("经核实的相关文档片段"); await wrapper.get("#negative-evidence").setValue("经核实的不相关文档片段");
    await wrapper.get("#positive-source").setValue("doc-positive"); await wrapper.get("#negative-source").setValue("doc-negative"); await wrapper.get("#review-note").setValue("已按问题核查来源");
    for(const checkbox of wrapper.findAll('.evidence-review-form input[type="checkbox"]')) await checkbox.setValue(true);
    await wrapper.get(".evidence-review-form").trigger("submit"); await flushPromises();
    expect(post).toHaveBeenCalledWith("/learning/flywheel/candidates/candidate-1/review/",expect.objectContaining({decision:"approve",positive_source:"doc-positive",negative_source:"doc-negative",redaction_confirmed:true,evidence_confirmed:true})); wrapper.unmount();
  });
  it("freezes only consented, approved selections and surfaces missing validation assets",async () => {
    flywheelGet({"/learning/flywheel/candidates/":{results:[{...candidate,status:"approved"}]},"/learning/flywheel/batches/":{results:[batch]}});
    const post=vi.spyOn(http,"post").mockImplementation(async url => { if(String(url).endsWith("/prepare/")) throw new ApiError("验证集未接入",400,"VALIDATION_DATA_MISSING"); return {data:batch}; });
    const wrapper=mount(FlywheelView,{global:await context("/flywheel")}); await flushPromises();
    await wrapper.get('input[aria-label="选择训练候选 candidate-1"]').setValue(true); await button(wrapper,"冻结所选").trigger("click"); await flushPromises();
    expect(post).toHaveBeenCalledWith("/learning/flywheel/batches/",{candidate_ids:["candidate-1"],label:""});
    await button(wrapper,"生成训练配置").trigger("click"); await flushPromises(); expect(wrapper.text()).toContain("验证集未接入"); expect(wrapper.find(".prepared-training").exists()).toBe(false); wrapper.unmount();
  });
  it("disables revoked feedback and invalidated batch actions",async () => {
    flywheelGet({"/learning/flywheel/candidates/":{results:[{...candidate,consent:false,status:"revoked"}]},"/learning/flywheel/batches/":{results:[{...batch,status:"invalidated"}]}});
    const wrapper=mount(FlywheelView,{global:await context("/flywheel")}); await flushPromises(); await button(wrapper,candidate.query).trigger("click");
    expect(wrapper.get(".evidence-review-form fieldset").attributes("disabled")).toBeDefined(); expect(button(wrapper,"下载 JSONL").attributes("disabled")).toBeDefined(); wrapper.unmount();
  });
  it("downloads only the requested frozen split and format",async () => {
    const BrowserURL=URL; const create=vi.fn(()=>"blob:local-download"); const revoke=vi.fn();
    vi.stubGlobal("URL",class extends BrowserURL {static createObjectURL=create;static revokeObjectURL=revoke;});
    const click=vi.spyOn(HTMLAnchorElement.prototype,"click").mockImplementation(()=>{});
    const get=flywheelGet({"/learning/flywheel/batches/":{results:[batch]},"/learning/flywheel/batches/batch-1/download/":new Blob(['{"query":"已审校问题"}\n'],{type:"application/x-ndjson"})});
    const wrapper=mount(FlywheelView,{global:await context("/flywheel")}); await flushPromises();
    await wrapper.get('[aria-label="训练数据格式"]').setValue("flagembedding"); await wrapper.get('[aria-label="导出数据划分"]').setValue("validation");
    await button(wrapper,"下载 JSONL").trigger("click"); await flushPromises();
    expect(get).toHaveBeenCalledWith("/learning/flywheel/batches/batch-1/download/",{params:{format:"flagembedding",split:"validation"},responseType:"blob"}); expect(click).toHaveBeenCalledOnce(); expect(revoke).toHaveBeenCalledWith("blob:local-download"); wrapper.unmount();
  });
  it("sorts the Agent list by the clinical engineering sequence",async () => {
    vi.spyOn(http,"get").mockImplementation(async url=>({data:url==="/agents/"?{agents:[{name:"safety"},{name:"debate"},{name:"retrieval"},{name:"triage"},{name:"medication"},{name:"explainer"},{name:"risk"}]}:{results:[]}}));
    const wrapper=mount(AgentsView,{global:await context("/agents")}); await flushPromises();
    const labels=wrapper.findAll(".agent-selector-item").map(item=>item.text());
    expect(labels).toHaveLength(7);
    expect(labels.map(label=>label.split(" ")[0])).toEqual(expect.arrayContaining([expect.stringContaining("问诊")]));
    expect(labels[0]).toContain("问诊"); expect(labels[1]).toContain("医学检索"); expect(labels[6]).toContain("安全护栏");
    wrapper.unmount();
  });
});
