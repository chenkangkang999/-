from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register
from agents.llm.support import emit_started, failure_result
from apps.consultations.services.clinical_medication import medication_audit


@register
class MedicationAgent(BaseAgent):
    name = "medication"
    description = "基于已审校药品/指南、NMPA映射和DDInter的用药审核；缺数据不排除风险"
    system_prompt = "你是临床药师，只给通用用药信息，不替代医生处方。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        emit_started(context, self.name)
        try:
            content, metadata, citations = medication_audit(context, message.content)
            return AgentResult(agent=self.name, content=content, citations=citations, metadata=metadata)
        except Exception as exc:
            return failure_result(self.name, exc)
