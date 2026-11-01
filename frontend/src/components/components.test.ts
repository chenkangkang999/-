import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import EvidenceList from "./EvidenceList.vue";
import SoapPanel from "./SoapPanel.vue";
import AgentTimeline from "./AgentTimeline.vue";
import SafetyAudit from "./SafetyAudit.vue";

describe("evidence rendering", () => {
  it("links real HTTP evidence and rejects executable source URLs", () => {
    const wrapper = mount(EvidenceList, {
      props: {
        citations: [
          {
            title: "官方指南",
            source: "https://example.org/guideline",
            snippet: "摘要",
            chunk_id: "chunk-a",
          },
          { title: "不可信链接", source: "javascript:alert(1)" },
          { title: "本地标识", source: "doc-123" },
        ],
      },
    });
    expect(wrapper.findAll("a")).toHaveLength(1);
    expect(wrapper.get("a").attributes("href")).toBe(
      "https://example.org/guideline",
    );
    expect(wrapper.get("a").attributes("rel")).toContain("noopener");
    expect(wrapper.text()).toContain("chunk-a");
    expect(wrapper.text()).toContain("本地标识");
  });
});
describe("SOAP summary", () => {
  it("renders structured explanation without executing model HTML", () => {
    const wrapper = mount(SoapPanel, {
      props: {
        soap: {
          subjective: "咳嗽三天",
          objective: "尚未提供检查",
          assessment: "待线下核实",
          plan: "观察变化",
        },
        explanation: "<script>alert(1)</script>",
        guidance: ["症状加重时就医", "携带检查资料"],
      },
    });
    expect(wrapper.text()).toContain("主观症状");
    expect(wrapper.text()).toContain("咳嗽三天");
    expect(wrapper.text()).toContain("症状加重时就医；携带检查资料");
    expect(wrapper.find("script").exists()).toBe(false);
  });
});
describe("agent timeline", () => {
  it("preserves failed and ongoing states instead of displaying fabricated completion", () => {
    const wrapper = mount(AgentTimeline, {
      props: {
        steps: [
          { agent: "retrieval", status: "running" },
          {
            agent: "safety",
            status: "failed",
            latency_ms: 42,
            error_code: "provider_timeout",
          },
        ],
      },
    });
    expect(wrapper.get("li.running").text()).toContain("进行中");
    expect(wrapper.get("li.failed").text()).toContain("provider_timeout");
    expect(wrapper.text()).toContain("42 ms");
  });
});

describe("final safety audit", () => {
  it("shows an approved audit without exposing candidate or approved raw fields", () => {
    const wrapper = mount(SafetyAudit, {
      props: {
        audit: {
          decision: "pass",
          severity: "low",
          reasons: ["符合健康信息参考范围"],
          regulations: [],
          candidate_text: "UNREVIEWED_CANDIDATE_DO_NOT_DISPLAY",
          approved_text: "RAW_FIELD_DO_NOT_DISPLAY",
        },
      },
    });
    expect(wrapper.text()).toContain("通过");
    expect(wrapper.text()).toContain("内容审核严重程度：低");
    expect(wrapper.text()).toContain("符合健康信息参考范围");
    expect(wrapper.text()).not.toContain("DO_NOT_DISPLAY");
  });
  it("shows blocked reasons and official clauses while filtering executable links", () => {
    const wrapper = mount(SafetyAudit, {
      props: {
        audit: {
          decision: "block",
          severity: "high",
          reasons: ["候选内容承诺由 AI 自动生成个人处方。"],
          regulations: [
            {
              title: "互联网诊疗监管细则（试行）",
              article: "第二十一条",
              summary: "处方由接诊医师开具",
              source_url: "https://www.nhc.gov.cn/verified-example.shtml",
            },
            { title: "不可信来源", source_url: "javascript:alert(1)" },
            { title: "禁止数据链接", source_url: "data:text/html,unsafe" },
          ],
        },
      },
    });
    expect(wrapper.text()).toContain("拦截");
    expect(wrapper.text()).toContain("内容审核严重程度：高");
    expect(wrapper.text()).toContain("第二十一条");
    expect(wrapper.text()).toContain("候选内容承诺由 AI 自动生成个人处方。");
    expect(wrapper.findAll("a")).toHaveLength(1);
    expect(wrapper.get("a").attributes("href")).toBe(
      "https://www.nhc.gov.cn/verified-example.shtml",
    );
    expect(wrapper.get("a").attributes("rel")).toContain("noopener");
    expect(wrapper.get("a").attributes("target")).toBe("_blank");
  });
  it("distinguishes a replacement and urgent risk from approval", () => {
    const wrapper = mount(SafetyAudit, {
      props: {
        audit: {
          decision: "replace",
          severity: "critical",
          reasons: ["优先急诊指引"],
        },
      },
    });
    expect(wrapper.text()).toContain("替换");
    expect(wrapper.text()).toContain("内容审核严重程度：极高");
    expect(wrapper.text()).not.toContain("通过");
  });
});
