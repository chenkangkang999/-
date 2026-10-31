"""协调器：固定编排 + 极简仲裁。

调度顺序：问诊 → 检索 → (风险评估 ∥ 用药) → 辩论 → 白话解释 → 安全护栏。
并发用线程池实现；任一 Agent 失败只降级该步，不中断链路。
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from agents.base.context import AgentContext
from agents.base.message import AgentMessage
from agents.base.registry import get_agent, load_all

PIPELINE = ("triage", "retrieval", "risk", "medication", "debate", "explainer", "safety")


@dataclass
class CoordinationResult:
    trace_id: str
    reply: str
    citations: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    risk_level: str = "low"
    blocked: bool = False

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "reply": self.reply,
            "citations": self.citations,
            "steps": self.steps,
            "risk_level": self.risk_level,
            "blocked": self.blocked,
        }


class Coordinator:
    def __init__(self, pipeline: tuple[str, ...] = PIPELINE, max_workers: int = 4) -> None:
        load_all()
        self.pipeline = pipeline
        self.max_workers = max_workers

    def run(self, text: str, context: AgentContext | None = None,
            enable_debate: bool = True) -> CoordinationResult:
        context = context or AgentContext()
        context.trace_id = context.trace_id or uuid.uuid4().hex
        message = AgentMessage(content=text)

        steps: list[dict] = []
        triage = get_agent("triage").run(context, message)
        steps.append(triage.to_dict())

        retrieval = get_agent("retrieval").run(context, message)
        steps.append(retrieval.to_dict())

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            risk_future = pool.submit(get_agent("risk").run, context, message)
            med_future = pool.submit(get_agent("medication").run, context, message)
            risk = risk_future.result()
            medication = med_future.result()
        steps.extend([risk.to_dict(), medication.to_dict()])

        debate = None
        if enable_debate:
            debate = get_agent("debate").run(context, message)
            steps.append(debate.to_dict())

        explainer = get_agent("explainer").run(context, message)
        steps.append(explainer.to_dict())

        safety = get_agent("safety").run(context, message)
        steps.append(safety.to_dict())

        reply = explainer.content or safety.content or "暂无法生成建议，请咨询线下医生。"
        risk_level = str(risk.metadata.get("risk_level", "low"))
        if risk_level == "high":
            reply = "检测到红旗征，请立即就医或拨打 120。\n" + reply
        citations = list(retrieval.citations)

        return CoordinationResult(
            trace_id=context.trace_id,
            reply=reply,
            citations=citations,
            steps=steps,
            risk_level=risk_level,
            blocked=bool(safety.metadata.get("blocked")),
        )
