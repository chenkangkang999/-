"""Transactional reservations and an injected, metered LLM adapter."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.billing.models import DailyBudget, UsageRecord, UsageReservation
from apps.billing.services.pricing import (
    BillingError,
    Price,
    budget_limits,
    calculate_cost,
    config,
    load_active_price,
)

# These failures do not establish whether the provider has already charged.
UNCERTAIN_PROVIDER_OUTCOMES = frozenset(
    {
        "TIMEOUT",
        "LLM_CONNECTION_ERROR",
        "LLM_PROVIDER_UNAVAILABLE",
        "INVALID_PROVIDER_RESPONSE",
    }
)


def reserve(user, tokens: int, cost: Decimal, *, call_id=None) -> UsageReservation:
    cost_limit, token_limit = budget_limits()
    if (
        isinstance(tokens, bool)
        or not isinstance(tokens, int)
        or tokens < 0
        or not cost.is_finite()
        or cost < 0
    ):
        raise BillingError("INVALID_USAGE")
    call_id = call_id or uuid.uuid4()
    with transaction.atomic():
        existing = UsageReservation.objects.filter(call_id=call_id).first()
        if existing:
            if (
                existing.budget.user_id != user.pk
                or existing.tokens != tokens
                or existing.cost != cost
            ):
                raise BillingError("IDEMPOTENCY_CONFLICT")
            return existing
        budget, _ = DailyBudget.objects.get_or_create(user=user, date=timezone.localdate())
        available = DailyBudget.objects.filter(
            pk=budget.pk, cost__lte=cost_limit - F("cost_reserved") - cost
        )
        if token_limit is not None:
            available = available.filter(
                tokens_used__lte=token_limit - F("tokens_reserved") - tokens
            )
        if (
            available.update(
                cost_reserved=F("cost_reserved") + cost,
                tokens_reserved=F("tokens_reserved") + tokens,
            )
            != 1
        ):
            raise BillingError("BUDGET_EXCEEDED")
        return UsageReservation.objects.create(
            call_id=call_id, budget=budget, tokens=tokens, cost=cost
        )


def release(call_id) -> None:
    with transaction.atomic():
        reservation = UsageReservation.objects.select_for_update().get(call_id=call_id)
        changed = UsageReservation.objects.filter(
            call_id=call_id, status=UsageReservation.Status.RESERVED
        ).update(status=UsageReservation.Status.RELEASED, completed_at=timezone.now())
        if changed:
            DailyBudget.objects.filter(pk=reservation.budget_id).update(
                tokens_reserved=F("tokens_reserved") - reservation.tokens,
                cost_reserved=F("cost_reserved") - reservation.cost,
            )


def settle(
    call_id,
    *,
    tokens_in: int,
    tokens_out: int,
    price: Price,
    provider: str,
    model: str,
    consultation=None,
    tokens_cached: int = 0,
    measurement: str = "provider",
    agent: str = "",
    trace_id: str = "",
    run_id: str = "",
    request_id: str | None = None,
) -> UsageRecord:
    amount = calculate_cost(tokens_in, tokens_out, price, tokens_cached=tokens_cached)
    with transaction.atomic():
        reservation = (
            UsageReservation.objects.select_for_update()
            .select_related("budget")
            .get(call_id=call_id)
        )
        existing = UsageRecord.objects.filter(call_id=call_id).first()
        if existing:
            return existing
        if reservation.status != UsageReservation.Status.RESERVED:
            raise BillingError("RESERVATION_NOT_ACTIVE")
        changed = UsageReservation.objects.filter(
            call_id=call_id, status=UsageReservation.Status.RESERVED
        ).update(status=UsageReservation.Status.SETTLED, completed_at=timezone.now())
        if changed != 1:
            raise BillingError("RESERVATION_NOT_ACTIVE")
        record = UsageRecord.objects.create(
            call_id=call_id,
            user_id=reservation.budget.user_id,
            consultation=consultation,
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cached=tokens_cached,
            cost=amount,
            measurement=measurement,
            price_snapshot=price.snapshot(),
            currency=price.currency,
            agent=agent,
            trace_id=trace_id,
            run_id=str(run_id),
            request_id=request_id or "",
        )
        DailyBudget.objects.filter(pk=reservation.budget_id).update(
            tokens_reserved=F("tokens_reserved") - reservation.tokens,
            cost_reserved=F("cost_reserved") - reservation.cost,
            tokens_used=F("tokens_used") + tokens_in + tokens_out,
            cost=F("cost") + amount,
        )
        return record


def estimate_tokens(text: str) -> int:
    """Only an estimate; the provider's usage remains authoritative."""
    import tiktoken

    try:
        encoding = tiktoken.get_encoding(config("BILLING_ESTIMATOR_ENCODING", "cl100k_base"))
    except Exception as exc:
        raise BillingError("BILLING_ESTIMATOR_UNAVAILABLE") from exc
    return len(encoding.encode(text, disallowed_special=()))


class MeteredLLM:
    def __init__(self, inner, *, user, consultation=None, trace_id="", run_id=""):
        self.inner = inner
        self.user = user
        self.consultation = consultation
        self.trace_id = trace_id
        self.run_id = str(run_id)
        self.model = getattr(inner, "model", None) or config("LLM_MODEL", "")
        self.provider = getattr(inner, "provider", None) or config("LLM_PROVIDER", "")

    def complete(self, system_prompt: str, user_prompt: str, *, agent: str):
        try:
            price, input_bound, output_bound, reservation = self._reserve(
                system_prompt, user_prompt
            )
        except BillingError as exc:
            self._failure(exc.code, agent)
            raise
        try:
            response = self.inner.complete(system_prompt, user_prompt, agent=agent)
        except Exception as exc:
            code = getattr(exc, "code", "LLM_CALL_FAILED")
            uncertain = code in UNCERTAIN_PROVIDER_OUTCOMES
            if not uncertain:
                release(reservation.call_id)
            self._failure(
                code, agent, reservation_call_id=reservation.call_id if uncertain else None
            )
            raise

        usage = response.usage
        tokens_in = usage.input_tokens if usage.input_tokens is not None else input_bound
        tokens_out = usage.output_tokens if usage.output_tokens is not None else output_bound
        measurement = (
            "provider"
            if usage.input_tokens is not None and usage.output_tokens is not None
            else "estimated"
        )
        try:
            record = settle(
                reservation.call_id,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                tokens_cached=getattr(usage, "input_cached_tokens", None) or 0,
                provider=self.provider,
                model=response.model or self.model,
                price=price,
                consultation=self.consultation,
                agent=agent,
                measurement=measurement,
                trace_id=self.trace_id,
                run_id=self.run_id,
                request_id=response.request_id,
            )
        except Exception:
            self._failure("USAGE_SETTLEMENT_FAILED", agent, reservation_call_id=reservation.call_id)
            raise
        if record.cost > reservation.cost or tokens_in + tokens_out > reservation.tokens:
            self._failure("PROVIDER_EXCEEDED_RESERVATION", agent)
            raise BillingError("BUDGET_EXCEEDED")
        return response

    def _reserve(self, system_prompt, user_prompt):
        price = load_active_price(self.provider, self.model)
        try:
            output_bound = int(
                getattr(self.inner, "max_tokens", config("LLM_MAX_OUTPUT_TOKENS", 2048))
            )
            overhead = int(config("BILLING_INPUT_TOKEN_OVERHEAD", 128))
        except (TypeError, ValueError) as exc:
            raise BillingError("BILLING_ESTIMATOR_INVALID") from exc
        if output_bound <= 0 or overhead < 0:
            raise BillingError("BILLING_ESTIMATOR_INVALID")
        prompt = system_prompt + "\n" + user_prompt
        input_bound = max(estimate_tokens(prompt), len(prompt.encode("utf-8"))) + overhead
        ceiling_price = Price(
            max(price.input_per_1k, price.cached_input_per_1k or price.input_per_1k),
            price.output_per_1k,
        )
        reservation = reserve(
            self.user,
            input_bound + output_bound,
            calculate_cost(input_bound, output_bound, ceiling_price),
        )
        return price, input_bound, output_bound, reservation

    def _failure(self, code: str, agent: str, *, reservation_call_id=None) -> None:
        from apps.monitoring.services import record_failure

        record_failure(
            code,
            source=agent,
            user=self.user,
            trace_id=self.trace_id,
            run_id=self.run_id,
            reservation_call_id=reservation_call_id,
        )
