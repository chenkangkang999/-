from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register


@register
class RiskAgent(BaseAgent):
    name = "risk"
    description = "紧急程度分级、红旗征筛查、就医路径建议"
    system_prompt = "你是急诊分诊医生，按低/中/高/极高四级评估紧急程度。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        flags: list[str] = context.facts.get("red_flags", [])
        level = "high" if flags else "low"
        action = "建议立即前往急诊" if flags else "可先线上问诊，必要时线下就医"
        return AgentResult(
            agent=self.name,
            content=f"紧急程度：{level}；{action}。",
            metadata={"risk_level": level, "red_flags": flags},
        )
