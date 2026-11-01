"""Integration entrypoints for teammate telemetry; no clinical payloads."""

from __future__ import annotations

from math import ceil, isfinite

from django.db.models import Avg, Count, Max, Q
from django.db.models.functions import TruncDate

from apps.agents.models import AgentRun
from apps.billing.models import UsageRecord
from apps.billing.services.pricing import config
from apps.billing.services.queries import usage_groups, usage_totals
from apps.consultations.models import Feedback
from apps.monitoring.models import FailureEvent, Metric
from apps.rag.models import Chunk, Document, IndexRun


def record_metric(
    name: str,
    value: float,
    *,
    user=None,
    trace_id: str = "",
    labels: dict | None = None,
    event_id: str | None = None,
) -> Metric:
    if not name or not isfinite(value):
        raise ValueError("invalid metric")
    fields = {
        "name": name,
        "value": value,
        "user": user,
        "trace_id": trace_id,
        "labels": labels or {},
    }
    if event_id:
        return Metric.objects.get_or_create(event_id=event_id, defaults=fields)[0]
    return Metric.objects.create(**fields)


def record_failure(
    code: str,
    *,
    source: str = "",
    user=None,
    trace_id: str = "",
    run_id: str = "",
    reservation_call_id=None,
) -> FailureEvent:
    if "BUDGET" in code or "RESERVATION" in code:
        kind = FailureEvent.Kind.BUDGET
    elif "TIMEOUT" in code:
        kind = FailureEvent.Kind.TIMEOUT
    elif "RATE_LIMIT" in code:
        kind = FailureEvent.Kind.RATE_LIMIT
    elif "PARSE" in code or "INVALID" in code:
        kind = FailureEvent.Kind.PARSE
    else:
        kind = FailureEvent.Kind.AGENT
    return FailureEvent.objects.create(
        kind=kind,
        source=source,
        user=user,
        trace_id=trace_id,
        run_id=str(run_id),
        message=code,
        payload=(
            {
                "reservation_call_id": str(reservation_call_id),
                "reservation_state": "held_for_reconciliation",
            }
            if reservation_call_id is not None
            else {}
        ),
    )


def percentile_99(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(ceil(len(ordered) * 0.99) - 1, 0)]


def get_overview(user, *, global_scope=False):
    global_scope = bool(user.is_staff and global_scope)
    runs = AgentRun.objects.all()
    failures = FailureEvent.objects.all()
    metrics = Metric.objects.all()
    usage = UsageRecord.objects.all()
    feedback = Feedback.objects.all()
    if not global_scope:
        runs = runs.filter(consultation__user=user)
        failures = failures.filter(user=user)
        metrics = metrics.filter(user=user)
        usage = usage.filter(user=user)
        feedback = feedback.filter(user=user)
    latency = runs.aggregate(avg=Avg("latency_ms"), max=Max("latency_ms"))
    retrieval_latency = list(
        metrics.filter(name="retrieval.latency_ms").values_list("value", flat=True)
    )
    hits = list(metrics.filter(name="retrieval.hit_count").values_list("value", flat=True))
    last_index = IndexRun.objects.filter(status=IndexRun.Status.SUCCEEDED).first()
    ratings = feedback.aggregate(
        count=Count("id"),
        positive=Count("id", filter=Q(rating=1)),
        negative=Count("id", filter=Q(rating=-1)),
    )
    ratings["positive_rate"] = ratings["positive"] / ratings["count"] if ratings["count"] else None
    by_agent = (
        runs.values("agent_name")
        .annotate(
            total=Count("id"),
            failed=Count("id", filter=Q(status=AgentRun.Status.FAILED)),
            avg_latency_ms=Avg("latency_ms"),
        )
        .order_by("agent_name")
    )
    days = usage_groups(usage.annotate(date=TruncDate("created_at")), "date")
    knowledge_connected = last_index is not None
    return {
        "scope": "all" if global_scope else "own",
        "agents": runs.aggregate(
            total=Count("id"),
            failed=Count("id", filter=Q(status=AgentRun.Status.FAILED)),
            blocked=Count("id", filter=Q(status=AgentRun.Status.BLOCKED)),
        ),
        "latency_ms": {"avg": latency["avg"], "max": latency["max"]},
        "knowledge": {
            "status": "connected" if knowledge_connected else "not_connected",
            "documents": Document.objects.count() if knowledge_connected else None,
            "chunks": Chunk.objects.count() if knowledge_connected else None,
            "last_indexed_at": last_index.finished_at if last_index else None,
        },
        "retrieval": {
            "status": "connected" if retrieval_latency or hits else "not_connected",
            "avg_latency_ms": sum(retrieval_latency) / len(retrieval_latency)
            if retrieval_latency
            else None,
            "p99_latency_ms": percentile_99(retrieval_latency),
            "no_hit_rate": sum(hit == 0 for hit in hits) / len(hits) if hits else None,
            "sample_count": len(retrieval_latency),
        },
        "cost": {
            "total": usage_totals(usage)["cost"],
            "currency": config("BILLING_CURRENCY", "CNY"),
            "by_day": days,
        },
        "feedback": ratings,
        "failures": failures.count(),
        "failure_modes": list(failures.values("kind").annotate(count=Count("id")).order_by("kind")),
        "by_agent": [
            {
                "agent": row["agent_name"],
                "total": row["total"],
                "failed": row["failed"],
                "avg_latency_ms": row["avg_latency_ms"],
            }
            for row in by_agent
        ],
        "services": {
            "retrieval_telemetry": "connected" if retrieval_latency or hits else "not_connected",
            "knowledge_index": "connected" if knowledge_connected else "not_connected",
            "billing": "connected" if usage.exists() else "no_data",
        },
    }
