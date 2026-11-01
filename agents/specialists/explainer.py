from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register
from agents.contracts import ExplanationOutput
from agents.llm.support import (
    complete_json,
    emit_started,
    evidence,
    failure_result,
    latest_steps,
    response_metadata,
    upstream_payload,
    validate_citation_ids,
)


@register
class ExplainerAgent(BaseAgent):
    name = "explainer"
    description = "将真实上游结果转换为 SOAP、通俗解释和就医指引，随后接受安全审核"
    system_prompt = "agents/prompts/explainer.md"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        emit_started(context, self.name)
        try:
            return self._explain(context, message)
        except Exception as exc:  # noqa: BLE001 - sanitize private model output errors
            return failure_result(self.name, exc)

    def _explain(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        result, response = complete_json(
            context, self.name, "explainer",
            upstream_payload(context, message, exclude=("explainer", "safety")),
            ExplanationOutput,
        )
        citations = evidence(context)
        validate_citation_ids(result.citation_ids, citations)
        soap = result.soap
        content = "\n\n".join([
            "【SOAP 小结】\n"
            f"S（你描述的情况）：{soap.subjective}\n"
            f"O（已知客观信息）：{soap.objective}\n"
            f"A（当前评估）：{soap.assessment}\n"
            f"P（后续安排）：{soap.plan}",
            f"【白话解释】\n{result.explanation}",
            "【就医指引】\n" + "\n".join(f"• {item}" for item in result.care_guidance),
        ])
        # These factual limitations are part of the candidate that Safety reviews,
        # rather than extra medical fields published outside the approval boundary.
        steps = latest_steps(context)
        additions = []
        triage = steps.get("triage", {})
        if triage.get("metadata", {}).get("differentials"):
            additions.append("【待医师核验的鉴别线索】\n" + triage["content"])
        for name, heading in (("risk", "风险数据核验"), ("medication", "用药数据核验")):
            step = steps.get(name, {})
            if step.get("metadata", {}).get("data_status") and step.get("content"):
                additions.append(f"【{heading}】\n{step['content']}")
        if additions:
            content += "\n\n" + "\n\n".join(additions)
        mandatory_ids = {item["chunk_id"] for name in ("risk", "medication") for item in steps.get(name, {}).get("citations", []) if isinstance(item, dict) and item.get("chunk_id")}
        return AgentResult(
            agent=self.name, content=content,
            citations=[item for item in citations if item["chunk_id"] in set(result.citation_ids) | mandatory_ids],
            metadata={**result.model_dump(), "llm": response_metadata(response),
                      "requires_safety_review": True},
        )
