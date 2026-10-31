"""会话级编排：把用户消息交给多智能体协调器，并落库（消息/运行记录/风险级别）。"""
from __future__ import annotations

import logging

from django.conf import settings

from agents.base.context import AgentContext
from agents.base.coordinator import Coordinator
from apps.agents.models import AgentRun
from apps.consultations.models import Consultation, Message

logger = logging.getLogger(__name__)


def _patient_facts(consultation: Consultation) -> dict:
    profile = getattr(consultation.user, "profile", None)
    if profile is None:
        return {}
    return {
        "allergies": profile.allergies,
        "chronic_conditions": profile.chronic_conditions,
        "current_medications": profile.current_medications,
    }


def run_consultation_turn(consultation: Consultation, message: Message) -> Message:
    context = AgentContext(
        consultation_id=consultation.pk,
        user_id=consultation.user_id,
        patient=_patient_facts(consultation),
    )
    try:
        result = Coordinator().run(
            message.content, context, enable_debate=settings.ENABLE_DEBATE
        )
    except Exception:  # noqa: BLE001 - 编排失败也要给用户可读的兜底
        logger.exception("consultation turn failed id=%s", consultation.pk)
        return Message.objects.create(
            consultation=consultation,
            role=Message.Role.ASSISTANT,
            content="抱歉，本次问诊处理失败，请稍后重试或直接线下就医。",
            agent_name="coordinator",
            citations=[],
        )

    reply = Message.objects.create(
        consultation=consultation,
        role=Message.Role.ASSISTANT,
        content=result.reply,
        agent_name="explainer",
        citations=result.citations,
    )

    Consultation.objects.filter(pk=consultation.pk).update(
        trace_id=result.trace_id,
        risk_level=result.risk_level,
        summary=result.reply[:2000],
        status=Consultation.Status.ESCALATED
        if result.risk_level == "high"
        else Consultation.Status.ACTIVE,
    )

    for step in result.steps:
        AgentRun.objects.create(
            consultation=consultation,
            agent_name=step.get("agent", "unknown"),
            status=AgentRun.Status.FAILED if step.get("error") else AgentRun.Status.SUCCEEDED,
            trace_id=result.trace_id,
            output_payload=step,
            latency_ms=step.get("latency_ms", 0),
            error=step.get("error") or "",
        )

    return reply
