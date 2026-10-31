"""计费核心：只在这里做「token → 金额」，避免各处四舍五入口径不一致。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

DEFAULT_INPUT_PER_1K = Decimal("0.001")
DEFAULT_OUTPUT_PER_1K = Decimal("0.002")


@dataclass(frozen=True)
class Price:
    input_per_1k: Decimal = DEFAULT_INPUT_PER_1K
    output_per_1k: Decimal = DEFAULT_OUTPUT_PER_1K


def load_active_price() -> Price:
    from apps.billing.models import PricePlan

    plan = PricePlan.objects.filter(is_active=True).order_by("-created_at").first()
    if plan is None:
        return Price()
    return Price(input_per_1k=plan.input_per_1k, output_per_1k=plan.output_per_1k)


def calculate_cost(tokens_in: int, tokens_out: int, price: Price | None = None) -> Decimal:
    price = price or load_active_price()
    return (
        Decimal(tokens_in) / Decimal(1000) * price.input_per_1k
        + Decimal(tokens_out) / Decimal(1000) * price.output_per_1k
    ).quantize(Decimal("0.000001"))


def record_usage(user, tokens_in: int, tokens_out: int, *, consultation=None,
                 model: str = "") -> Decimal:
    from django.utils import timezone

    from apps.billing.models import DailyBudget, UsageRecord

    cost = calculate_cost(tokens_in, tokens_out)
    UsageRecord.objects.create(
        user=user, consultation=consultation, model=model,
        tokens_in=tokens_in, tokens_out=tokens_out, cost=cost,
    )
    today = timezone.localdate()
    budget, _ = DailyBudget.objects.get_or_create(user=user, date=today)
    DailyBudget.objects.filter(pk=budget.pk).update(
        tokens_used=budget.tokens_used + tokens_in + tokens_out,
        cost=budget.cost + cost,
    )
    return cost
