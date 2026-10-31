from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register


@register
class DebateAgent(BaseAgent):
    name = "debate"
    description = "多 Agent 意见分歧时的质证与收敛（接口占位，P3 接 LangGraph）"
    system_prompt = "你是主持医生，负责归纳分歧并给出收敛意见。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        disagreements: list[str] = []
        if context.facts.get("red_flags"):
            disagreements.append("急诊派 vs 观察派：红旗征存在，倾向急诊")
        return AgentResult(
            agent=self.name,
            content="辩论收敛：以安全侧结论为准。" if disagreements else "各 Agent 意见一致，无需辩论。",
            metadata={"disagreements": disagreements},
        )
