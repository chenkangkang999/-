from __future__ import annotations

from agents.base.agent import AgentResult, BaseAgent
from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import register

RED_FLAGS = ("胸痛", "呼吸困难", "意识不清", "抽搐", "大出血", "晕厥", "剧烈头痛")


@register
class TriageAgent(BaseAgent):
    name = "triage"
    description = "多轮追问、症状标准化、红旗征识别"
    system_prompt = "你是问诊医生，负责结构化采集主诉并识别红旗征。"

    def _execute(self, context: AgentContext, message: AgentMessage) -> AgentResult:
        text = message.content
        flags = [word for word in RED_FLAGS if word in text]
        context.facts["red_flags"] = flags
        context.facts["chief_complaint"] = text[:200]
        return AgentResult(
            agent=self.name,
            content="已记录主诉，继续追问伴随症状与持续时间。",
            metadata={"red_flags": flags, "need_followup": not text.strip()},
        )
