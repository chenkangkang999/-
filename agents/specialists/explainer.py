from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register


@register
class ExplainerAgent(BaseAgent):
    name = "explainer"
    description = "把医学结论翻译成普通人能听懂的话（SOAP + 就医指引）"
    system_prompt = "你是健康科普编辑，用初中生能懂的话解释，不夸大、不吓人。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        complaint = context.facts.get("chief_complaint", message.content)[:120]
        risk = "需要尽快就医" if context.facts.get("red_flags") else "可以先观察"
        reply = (
            f"【你的情况】{complaint}\n"
            f"【初步判断】现有信息不足以下诊断，{risk}。\n"
            "【建议】补充症状持续时间、体温与既往病史，必要时到线下就诊。\n"
            "【提醒】本回答不替代医生面诊。"
        )
        return AgentResult(agent=self.name, content=reply)
