import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { http } from "@/api/client";
import ClinicalInputs from "./ClinicalInputs.vue";
import RagStatus from "./RagStatus.vue";
afterEach(() => vi.restoreAllMocks());
describe("clinical inputs and actual retrieval", () => {
  it("keeps unknown empty and submits explicit false rather than assuming no", async () => {
    vi.spyOn(http,"get").mockResolvedValue({data:{note:"仅填已知",fields:[{id:"pregnancy",label:"是否妊娠",group:"特殊情况",type:"boolean"}]}});
    const wrapper=mount(ClinicalInputs,{props:{modelValue:{}}}); await flushPromises();
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    await wrapper.get("select").setValue("false");
    expect(wrapper.emitted("update:modelValue")?.[0]?.[0]).toEqual({pregnancy:false});
    await wrapper.get("select").setValue("");
    expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toEqual({});
  });
  it("shows BM25 and real index counts without claiming BGE is enabled", async () => {
    vi.spyOn(http,"get").mockResolvedValue({data:{mode:"bm25",status:"connected",degraded_reason:"CPU降级，未启用BGE",base_model_present:false,active_adapter_consumed:false,reranker:"none",clinical_data:{ddi:{status:"not_connected"}},index:{id:5,status:"succeeded",processed_rows:42,total_rows:42,documents:7,chunks:8,deduplicated:35,full_corpus:true,limited:false,error_code:""}}});
    const wrapper=mount(RagStatus,{global:{plugins:[ElementPlus]}}); await flushPromises();
    expect(wrapper.text()).toContain("真实 BM25"); expect(wrapper.text()).toContain("42 / 42"); expect(wrapper.text()).toContain("未接入"); expect(wrapper.text()).toContain("尚未被当前检索模式使用");
    expect(wrapper.text()).not.toContain("61,987"); wrapper.unmount();
  });
  it("does not invent progress when no index exists", async () => {
    vi.spyOn(http,"get").mockResolvedValue({data:{mode:"bm25",status:"not_connected",clinical_data:{},index:null}});
    const wrapper=mount(RagStatus,{global:{plugins:[ElementPlus]}}); await flushPromises();
    expect(wrapper.text()).toContain("尚未运行知识索引"); expect(wrapper.find('[role="progressbar"]').exists()).toBe(false); wrapper.unmount();
  });
});
