"""协调器：固定编排 + 极简仲裁。

调度顺序：问诊 → 检索 → (风险评估 ∥ 用药) → 辩论 → 白话解释 → 安全护栏。
并发用线程池实现；任一 Agent 失败只降级该步，不中断链路。
"""
from __future__ import annotations

import os
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
    def __init__(self, pipeline: tuple[str, ...] = PIPELINE, max_workers: int | None = None) -> None:
        load_all()
        self.pipeline = pipeline
        self.max_workers = int(os.getenv("COORDINATOR_WORKERS", "4")) if max_workers is None else max_workers
        if self.max_workers <= 0:
            raise ValueError("COORDINATOR_WORKERS must be positive")

    def run(self, text: str, context: AgentContext | None = None,
            enable_debate: bool = True) -> CoordinationResult:
        context = context or AgentContext()
        context.trace_id = context.trace_id or uuid.uuid4().hex
        message = AgentMessage(content=text)

        steps: list[dict] = []
        triage = get_agent("triage").run(context, message)
        steps.append(triage.to_dict())

        if triage.metadata.get("red_flags") or triage.metadata.get("need_followup"):
            risk = None
            if triage.metadata.get("red_flags"):
                risk = get_agent("risk").run(context, message)
                steps.append(risk.to_dict())
            context.facts["candidate_text"] = triage.content
            safety = get_agent("safety").run(context, message)
            steps.append(safety.to_dict())
            return self._approved_result(context, steps, risk, safety, [])

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

        return self._approved_result(context, steps, risk, safety, explainer.citations)

    @staticmethod
    def _approved_result(context, steps, risk, safety, citations):
        audit = safety.metadata
        valid = not safety.error and audit.get("decision") in {"pass", "replace", "block"} and isinstance(audit.get("approved_text"), str) and bool(audit["approved_text"].strip())
        reply = audit["approved_text"].strip() if valid else "安全审核未完成，本轮不提供未经审核的建议，请咨询线下医师。"
        risk_level = str(risk.metadata.get("risk_level", "unknown")) if risk else "unknown"
        if risk and risk.metadata.get("risk_level_is_provisional") and risk_level == "low":
            risk_level = "unknown"
        if audit.get("escalate") or audit.get("severity") == "critical":
            risk_level = "critical"
        return CoordinationResult(
            trace_id=context.trace_id,
            reply=reply,
            citations=list(citations) if valid and audit["decision"] == "pass" else [],
            steps=steps,
            risk_level=risk_level,
            blocked=not valid or audit.get("decision") != "pass",
        )
