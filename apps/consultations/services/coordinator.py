"""Web publication boundary: never trust an unreviewed Coordinator.reply."""

from __future__ import annotations

import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from agents.base.context import AgentContext
from apps.agents.models import AgentRun
from apps.consultations.models import Consultation, ConsultationRun, Message
from apps.consultations.services.events import publish

logger = logging.getLogger(__name__)
_executor = None
_executor_lock = threading.Lock()


class ActiveRunError(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


class PublicationError(Exception):
    def __init__(self, message, code="SAFETY_UNAVAILABLE"):
        self.code = code
        super().__init__(message)


def safe_error_code(value, default="AGENT_EXECUTION_FAILED"):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", value)
        else default
    )


class LazyMeteredLLM:
    """Defers model configuration so deterministic emergency exits remain available."""

    def __init__(self, run):
        self.run = run
        self.inner = None
        self.lock = threading.Lock()

    def complete(self, system_prompt, user_prompt, *, agent):
        with self.lock:
            if self.inner is None:
                from agents.llm import get_llm_client
                from apps.billing.services.metering import MeteredLLM

                self.inner = MeteredLLM(
                    inner=get_llm_client(),
                    user=self.run.consultation.user,
                    consultation=self.run.consultation,
                    trace_id=self.run.trace_id,
                    run_id=str(self.run.pk),
                )
        return self.inner.complete(system_prompt, user_prompt, agent=agent)


def error_code(exc):
    name = type(exc).__name__.lower()
    configured = getattr(exc, "code", None)
    if configured:
        return safe_error_code(str(configured), "EXECUTION_FAILED")
    if "timeout" in name:
        return "TIMEOUT"
    if "budget" in name:
        return "BUDGET_EXCEEDED"
    if "configuration" in name or "config" in name:
        return "CONFIGURATION_REQUIRED"
    return "EXECUTION_FAILED"


def create_run(consultation, content, client_request_id):
    existing = ConsultationRun.objects.filter(
        consultation=consultation, client_request_id=client_request_id
    ).first()
    if existing:
        if existing.message.content != content:
            raise IdempotencyConflict("同一请求标识不能对应不同内容")
        return existing, False
    try:
        with transaction.atomic():
            if ConsultationRun.objects.filter(
                consultation=consultation, status__in=["pending", "running"]
            ).exists():
                raise ActiveRunError("当前会话仍有任务运行，请等待完成")
            message = Message.objects.create(
                consultation=consultation, role=Message.Role.USER, content=content
            )
            run = ConsultationRun.objects.create(
                consultation=consultation,
                message=message,
                client_request_id=client_request_id,
                trace_id=uuid.uuid4().hex,
            )
            return run, True
    except IntegrityError:
        existing = ConsultationRun.objects.filter(
            consultation=consultation, client_request_id=client_request_id
        ).first()
        if existing:
            if existing.message.content != content:
                raise IdempotencyConflict("同一请求标识不能对应不同内容") from None
            return existing, False
        raise ActiveRunError("当前会话仍有任务运行，请等待完成") from None


@dataclass
class WebContext(AgentContext):
    """Adapt the existing synchronous record hook, including parallel specialist threads."""

    def configure(self, run):
        self._run = run
        self._record_lock = threading.RLock()
        self.facts["_emit"] = self.emit
        return self

    def emit(self, agent, status, payload=None):
        # Arbitrary provider payloads must never cross the pre-review channel.
        allowed = {}
        if payload:
            for key in ("latency_ms", "round", "error_code"):
                if key in payload:
                    allowed[key] = payload[key]
        publish(
            self.consultation_id,
            run_id=self._run.pk,
            trace_id=self.trace_id,
            event_type=f"agent.{status}",
            agent=agent,
            status=status,
            payload=allowed,
        )

    def record(self, agent, payload):
        with self._record_lock:
            super().record(agent, payload)
            failed = bool(payload.get("error"))
            metadata = payload.get("metadata", {})
            failure_code = (
                safe_error_code(metadata.get("error_code") or payload.get("error"))
                if failed
                else ""
            )
            blocked = metadata.get("decision") == "block"
            # Persist operational data only. Internal candidate text stays in memory.
            public_metadata = {
                key: metadata[key]
                for key in ("decision", "severity", "blocked", "status")
                if key in metadata
            }
            from django.db.models import Sum

            from apps.billing.models import UsageRecord

            usage = UsageRecord.objects.filter(trace_id=self.trace_id, agent=agent).aggregate(
                tokens_in=Sum("tokens_in"), tokens_out=Sum("tokens_out"), cost=Sum("cost")
            )
            AgentRun.objects.create(
                consultation_id=self.consultation_id,
                agent_name=agent,
                trace_id=self.trace_id,
                status=AgentRun.Status.FAILED
                if failed
                else (AgentRun.Status.BLOCKED if blocked else AgentRun.Status.SUCCEEDED),
                latency_ms=payload.get("latency_ms", 0),
                tokens_in=usage["tokens_in"] or 0,
                tokens_out=usage["tokens_out"] or 0,
                cost=usage["cost"] or 0,
                output_payload={"agent": agent, "metadata": public_metadata},
                error=failure_code,
            )
            self.emit(
                agent,
                "failed" if failed else "completed",
                {
                    "latency_ms": payload.get("latency_ms", 0),
                    "error_code": failure_code,
                },
            )


def _patient_facts(consultation):
    profile = getattr(consultation.user, "profile", None)
    if profile is None:
        return {}
    return {
        "allergies": profile.allergies,
        "chronic_conditions": profile.chronic_conditions,
        "current_medications": profile.current_medications,
        "birth_date": str(profile.birth_date) if profile.birth_date else None,
        "sex": profile.sex,
    }


def approved_output(steps):
    safety = next((s for s in reversed(steps) if s.get("agent") == "safety"), None)
    if not safety or safety.get("error"):
        code = safe_error_code(safety.get("error") if safety else None, "SAFETY_UNAVAILABLE")
        raise PublicationError("安全审核未完成，候选回复未发布", code)
    audit = safety.get("metadata", {})
    decision = audit.get("decision")
    text = audit.get("approved_text")
    if (
        decision not in {"pass", "replace", "block"}
        or not isinstance(text, str)
        or not text.strip()
    ):
        raise PublicationError("安全审核结果无效，候选回复未发布")
    return text.strip(), audit


def _prepare_context(run):
    consultation = run.consultation
    context = WebContext(
        consultation_id=consultation.pk,
        user_id=consultation.user_id,
        trace_id=run.trace_id,
        patient=_patient_facts(consultation),
    ).configure(run)
    history = import_string(settings.HISTORY_PROVIDER)()
    context.facts["history"] = history.load(consultation.pk, before_message_id=run.message_id)
    context.facts["_llm"] = LazyMeteredLLM(run)
    return context


def execute_run(run_id):
    # Atomic claim prevents duplicate task delivery from executing twice.
    claimed = ConsultationRun.objects.filter(pk=run_id, status="pending").update(
        status="running", started_at=timezone.now()
    )
    if not claimed:
        return
    run = ConsultationRun.objects.select_related("consultation__user", "message").get(pk=run_id)
    publish(
        run.consultation_id,
        run_id=run.pk,
        trace_id=run.trace_id,
        event_type="run.started",
        status="running",
    )
    try:
        context = _prepare_context(run)
        if run.metadata.get("test_agent"):
            from types import SimpleNamespace

            from agents.base.message import AgentMessage
            from agents.base.registry import get_agent, load_all

            load_all()
            name = run.metadata["test_agent"]
            if name == "safety":
                context.facts["candidate_text"] = run.message.content
            tested = get_agent(name).run(context, AgentMessage(content=run.message.content))
            if name != "safety":
                context.facts["candidate_text"] = tested.content
                get_agent("safety").run(context, AgentMessage(content=run.message.content))
            result = SimpleNamespace(steps=context.steps, risk_level="low")
        else:
            provider = import_string(settings.COORDINATOR_PROVIDER)()
            result = provider.run(
                run.message.content, context, enable_debate=settings.ENABLE_DEBATE
            )
        steps = context.steps or result.steps
        text, audit = approved_output(steps)
        risk = (
            "critical"
            if audit.get("escalate") or audit.get("severity") == "critical"
            else audit.get("risk_level", result.risk_level)
        )
        if risk not in Consultation.RiskLevel.values:
            risk = Consultation.RiskLevel.LOW
        explainer = next((s for s in reversed(steps) if s.get("agent") == "explainer"), {})
        # Structured explanation is only exposed when its full text passed the gate.
        details = explainer.get("metadata", {}) if audit["decision"] == "pass" else {}
        details = (
            {
                "soap": details.get("soap"),
                "plain_explanation": details.get("explanation"),
                "guidance": details.get("care_guidance"),
            }
            if details
            else {}
        )
        details["safety"] = {
            k: audit[k] for k in ("decision", "severity", "regulations", "reasons") if k in audit
        }
        citations = explainer.get("citations", []) if audit["decision"] == "pass" else []
        from django.db.models import Sum

        from apps.billing.models import UsageRecord

        totals = UsageRecord.objects.filter(trace_id=run.trace_id).aggregate(
            tokens_in=Sum("tokens_in"), tokens_out=Sum("tokens_out")
        )
        with transaction.atomic():
            reply = Message.objects.create(
                consultation=run.consultation,
                role=Message.Role.ASSISTANT,
                content=text,
                agent_name="safety",
                citations=citations,
                tokens_in=totals["tokens_in"] or 0,
                tokens_out=totals["tokens_out"] or 0,
            )
            run.reply = reply
            run.status = "blocked" if audit["decision"] == "block" else "succeeded"
            run.metadata = details
            run.finished_at = timezone.now()
            run.save(update_fields=["reply", "status", "metadata", "finished_at"])
            Consultation.objects.filter(pk=run.consultation_id).update(
                trace_id=run.trace_id,
                risk_level=risk,
                summary=text[:2000],
                status="escalated"
                if risk == "critical"
                else ("awaiting_review" if risk == "high" else "active"),
                updated_at=timezone.now(),
            )
        size = settings.ANSWER_CHUNK_SIZE
        for start in range(0, len(text), size):
            publish(
                run.consultation_id,
                run_id=run.pk,
                trace_id=run.trace_id,
                event_type="answer.chunk",
                payload={"text": text[start : start + size]},
            )
        publish(
            run.consultation_id,
            run_id=run.pk,
            trace_id=run.trace_id,
            event_type="run.completed",
            status=run.status,
        )
    except Exception as exc:
        code = error_code(exc)
        # Do not store the exception body: providers may embed prompts or medical candidates.
        logger.warning("Run failed trace=%s kind=%s", run.trace_id, type(exc).__name__)
        ConsultationRun.objects.filter(pk=run.pk).update(
            status="failed",
            finished_at=timezone.now(),
            error={
                "code": code,
                "message": "本次运行未完成，未发布未经审核的回复。请检查服务配置或联系管理员。",
            },
        )
        from apps.monitoring.services import record_failure

        record_failure(
            code,
            source="consultation",
            user=run.consultation.user,
            trace_id=run.trace_id,
            run_id=str(run.pk),
        )
        publish(
            run.consultation_id,
            run_id=run.pk,
            trace_id=run.trace_id,
            event_type="run.failed",
            status="failed",
            payload={"error_code": code},
        )


def _background_run(run_id):
    close_old_connections()
    try:
        execute_run(run_id)
    finally:
        close_old_connections()


def dispatch_run(run):
    mode = settings.CONSULTATION_EXECUTOR
    if mode == "inline":
        execute_run(run.pk)
    elif mode == "celery":
        from apps.consultations.tasks import execute_consultation

        execute_consultation.delay(str(run.pk))
    elif mode == "thread":
        global _executor
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=settings.CONSULTATION_WORKERS)
        _executor.submit(_background_run, run.pk)
    else:
        raise ValueError("CONSULTATION_EXECUTOR must be inline, thread or celery")


def run_consultation_turn(consultation, message):
    """Preserve the synchronous entry point; all replies still pass the same gate."""
    run = ConsultationRun.objects.create(
        consultation=consultation,
        message=message,
        client_request_id=uuid.uuid4(),
        trace_id=uuid.uuid4().hex,
    )
    execute_run(run.pk)
    run.refresh_from_db()
    return run.reply
