from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register
from agents.llm.support import emit_started, failure_result
from apps.consultations.services.clinical_risk import assess_risk


@register
class RiskAgent(BaseAgent):
    name = "risk"
    description = "急症优先、完整NEWS2生命体征审核与可追溯的FHS原公式；缺字段不计算"
    system_prompt = "结构化风险审核，不输出未经验证的诊断概率或自动治疗。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        emit_started(context, self.name)
        try:
            content, metadata, citations = assess_risk(context, message.content)
            return AgentResult(agent=self.name, content=content, citations=citations, metadata=metadata)
        except Exception as exc:
            return failure_result(self.name, exc)
