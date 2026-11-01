"""Shared billing aggregates used by billing and monitoring APIs."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.billing.models import DailyBudget, UsageRecord
from apps.billing.services.pricing import BillingError, budget_limits, config, load_active_price


def money_text(value) -> str:
    """Return the ledger's six-decimal precision, including empty aggregates."""
    return format(Decimal(value or 0).quantize(Decimal("0.000001")), ".6f")


def usage_totals(qs):
    totals = qs.aggregate(
        input_tokens=Sum("tokens_in"), output_tokens=Sum("tokens_out"), cost=Sum("cost")
    )
    input_tokens = totals["input_tokens"] or 0
    output_tokens = totals["output_tokens"] or 0
    return {
        "tokens": input_tokens + output_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": money_text(totals["cost"]),
    }


def usage_groups(qs, *fields):
    rows = (
        qs.values(*fields)
        .annotate(input_tokens=Sum("tokens_in"), output_tokens=Sum("tokens_out"), cost=Sum("cost"))
        .order_by(*fields)
    )
    return [
        {
            **{field: row[field] for field in fields},
            "tokens": row["input_tokens"] + row["output_tokens"],
            "cost": money_text(row["cost"]),
        }
        for row in rows
    ]


def get_usage_summary(user, *, global_scope=False):
    global_scope = bool(user.is_staff and global_scope)
    qs = UsageRecord.objects.all() if global_scope else UsageRecord.objects.filter(user=user)
    by_day = usage_groups(qs.annotate(date=TruncDate("created_at")), "date")
    by_user = usage_groups(qs, "user_id", "user__username") if global_scope else []
    latest = qs.order_by("-created_at")[:50]
    return {
        "scope": "all" if global_scope else "own",
        "today": usage_totals(qs.filter(created_at__date=timezone.localdate())),
        "total": usage_totals(qs),
        "records": qs.count(),
        "currency": config("BILLING_CURRENCY", "CNY"),
        "measurement": {
            row["measurement"]: row["count"]
            for row in qs.values("measurement").annotate(count=Count("id"))
        },
        "by_day": by_day,
        "by_query": usage_groups(qs, "consultation_id"),
        "by_run": usage_groups(qs.exclude(run_id=""), "run_id", "consultation_id"),
        "by_user": [
            {
                "user_id": row["user_id"],
                "username": row["user__username"],
                "tokens": row["tokens"],
                "cost": row["cost"],
            }
            for row in by_user
        ],
        "latest": [
            {
                "id": row.pk,
                "call_id": str(row.call_id),
                "agent": row.agent,
                "model": row.model,
                "run_id": row.run_id,
                "trace_id": row.trace_id,
                "tokens_in": row.tokens_in,
                "tokens_out": row.tokens_out,
                "tokens_cached": row.tokens_cached,
                "cost": money_text(row.cost),
                "currency": row.currency,
                "measurement": row.measurement,
                "created_at": row.created_at,
            }
            for row in latest
        ],
    }


def get_budget_summary(user):
    budget = DailyBudget.objects.filter(user=user, date=timezone.localdate()).first()
    cost = budget.cost if budget else 0
    reserved_cost = budget.cost_reserved if budget else 0
    try:
        cost_limit, token_limit = budget_limits()
        configured = True
        remaining_cost = money_text(max(cost_limit - cost - reserved_cost, 0))
    except BillingError:
        cost_limit, token_limit, configured, remaining_cost = (None, None, False, None)
    try:
        load_active_price()
        price_configured = True
    except BillingError:
        price_configured = False
    return {
        "date": timezone.localdate(),
        "tokens_used": budget.tokens_used if budget else 0,
        "cost": money_text(cost),
        "reserved_cost": money_text(reserved_cost),
        "reserved_tokens": budget.tokens_reserved if budget else 0,
        "cost_limit": str(cost_limit) if cost_limit is not None else None,
        "token_limit": token_limit,
        "currency": config("BILLING_CURRENCY", "CNY"),
        "configured": configured,
        "price_configured": price_configured,
        "remaining_cost": remaining_cost,
    }
