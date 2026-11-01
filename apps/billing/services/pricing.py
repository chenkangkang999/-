"""Versioned, explicit pricing. No fallback prices are silently invented."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone


class BillingError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def config(name: str, default=None):
    return getattr(settings, name, os.getenv(name, default))


@dataclass(frozen=True)
class Price:
    input_per_1k: Decimal
    output_per_1k: Decimal
    cached_input_per_1k: Decimal | None = None
    currency: str = "CNY"
    plan_id: int | None = None
    name: str = ""

    def snapshot(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "input_per_1k": str(self.input_per_1k),
            "output_per_1k": str(self.output_per_1k),
            "cached_input_per_1k": (
                str(self.cached_input_per_1k) if self.cached_input_per_1k is not None else None
            ),
            "currency": self.currency,
        }


def load_active_price(provider: str | None = None, model: str | None = None) -> Price:
    from apps.billing.models import PricePlan

    provider = provider or config("LLM_PROVIDER", "")
    model = model or config("LLM_MODEL", "")
    if not provider or not model:
        raise BillingError("PRICE_NOT_CONFIGURED")
    plan = (
        PricePlan.objects.filter(
            provider=provider, model=model, is_active=True, effective_from__lte=timezone.now()
        )
        .order_by("-effective_from", "-id")
        .first()
    )
    if plan is None:
        raise BillingError("PRICE_NOT_CONFIGURED")
    amounts = [plan.input_per_1k, plan.output_per_1k]
    if plan.cached_input_per_1k is not None:
        amounts.append(plan.cached_input_per_1k)
    if any(not amount.is_finite() or amount < 0 for amount in amounts):
        raise BillingError("PRICE_INVALID")
    if plan.currency != config("BILLING_CURRENCY", "CNY"):
        raise BillingError("BILLING_CURRENCY_MISMATCH")
    return Price(
        plan.input_per_1k,
        plan.output_per_1k,
        plan.cached_input_per_1k,
        plan.currency,
        plan.pk,
        plan.name,
    )


def calculate_cost(
    tokens_in: int, tokens_out: int, price: Price | None = None, *, tokens_cached: int = 0
) -> Decimal:
    if (
        any(
            isinstance(v, bool) or not isinstance(v, int) or v < 0
            for v in (tokens_in, tokens_out, tokens_cached)
        )
        or tokens_cached > tokens_in
    ):
        raise BillingError("INVALID_USAGE")
    price = price or load_active_price()
    cached_price = (
        price.cached_input_per_1k if price.cached_input_per_1k is not None else price.input_per_1k
    )
    return (
        Decimal(tokens_in - tokens_cached) / Decimal(1000) * price.input_per_1k
        + Decimal(tokens_cached) / Decimal(1000) * cached_price
        + Decimal(tokens_out) / Decimal(1000) * price.output_per_1k
    ).quantize(Decimal("0.000001"))


def budget_limits() -> tuple[Decimal, int | None]:
    try:
        money = Decimal(str(config("DAILY_COST_BUDGET_PER_USER", "")))
        raw_tokens = config("DAILY_TOKEN_BUDGET_PER_USER", "")
        tokens = int(raw_tokens) if str(raw_tokens).strip() else None
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BillingError("BUDGET_NOT_CONFIGURED") from exc
    if not money.is_finite() or money <= 0 or (tokens is not None and tokens <= 0):
        raise BillingError("BUDGET_NOT_CONFIGURED")
    return money, tokens


def record_usage(
    user,
    tokens_in: int,
    tokens_out: int,
    *,
    consultation=None,
    model: str = "",
    provider: str = "",
    call_id=None,
) -> Decimal:
    """Compatibility entrypoint for teammates reporting measured, real usage."""
    from apps.billing.models import UsageRecord
    from apps.billing.services.metering import reserve, settle

    if call_id:
        previous = UsageRecord.objects.filter(call_id=call_id).first()
        if previous:
            if (
                previous.user_id != user.pk
                or previous.tokens_in != tokens_in
                or previous.tokens_out != tokens_out
            ):
                raise BillingError("IDEMPOTENCY_CONFLICT")
            return previous.cost
    price = load_active_price(provider or None, model or None)
    reservation = reserve(
        user, tokens_in + tokens_out, calculate_cost(tokens_in, tokens_out, price), call_id=call_id
    )
    return settle(
        reservation.call_id,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        price=price,
        consultation=consultation,
        model=model or config("LLM_MODEL", ""),
        provider=provider or config("LLM_PROVIDER", ""),
    ).cost
