from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register

DISCLAIMER = "以上内容仅供健康参考，不能替代执业医师的诊断与处方。"
BLOCK_PATTERNS = ("开个处方", "直接吃多少毫克", "不用去医院")


@register
class SafetyAgent(BaseAgent):
    name = "safety"
    description = "合规审核：拦截越界用药建议、强制免责声明、极高风险转急诊"
    system_prompt = "你是医疗合规审核员，宁可拦截也不放过风险。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        text = message.content
        blocked = any(pattern in text for pattern in BLOCK_PATTERNS)
        critical = bool(context.facts.get("red_flags"))
        content = DISCLAIMER
        if critical:
            content = "检测到红旗征，建议立即急诊。" + DISCLAIMER
        return AgentResult(
            agent=self.name,
            content=content,
            metadata={"blocked": blocked, "escalate": critical},
        )
