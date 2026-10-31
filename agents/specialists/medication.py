from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register


@register
class MedicationAgent(BaseAgent):
    name = "medication"
    description = "用药推荐、相互作用与禁忌筛查、特殊人群剂量提示"
    system_prompt = "你是临床药师，只给通用用药信息，不替代医生处方。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        allergies = context.patient.get("allergies") or []
        note = "请告知过敏史与在用药物，药师可进一步核对相互作用。"
        if allergies:
            note = f"已知过敏史 {allergies}，用药前必须再次核对。"
        return AgentResult(
            agent=self.name,
            content=f"用药建议需由医生确认。{note}",
            metadata={"requires_doctor": True, "allergies": allergies},
        )
