from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from agents.contracts import LLMResponse, LLMUsage
from apps.billing.models import DailyBudget, PricePlan, UsageRecord, UsageReservation
from apps.billing.services.metering import MeteredLLM, release, reserve, settle
from apps.billing.services.pricing import BillingError, Price, calculate_cost, load_active_price

pytestmark = pytest.mark.django_db


@pytest.fixture
def billing_setup(settings, django_user_model, monkeypatch):
    settings.LLM_PROVIDER = "test-provider"
    settings.LLM_MODEL = "test-model"
    settings.BILLING_CURRENCY = "CNY"
    settings.DAILY_COST_BUDGET_PER_USER = "2"
    settings.DAILY_TOKEN_BUDGET_PER_USER = 100000
    settings.LLM_MAX_OUTPUT_TOKENS = 256
    settings.BILLING_INPUT_TOKEN_OVERHEAD = 128
    monkeypatch.setattr("apps.billing.services.metering.estimate_tokens", lambda text: len(text))
    user = django_user_model.objects.create_user(username="billing-user", password="test-pass-123")
    plan = PricePlan.objects.create(
        name="explicit-test-fixture",
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
        input_per_1k="0.01",
        output_per_1k="0.02",
        cached_input_per_1k="0.002",
    )
    return user, plan


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def fake_inner(*, usage=None, error=None):
    response = LLMResponse(
        "fixture response", usage or LLMUsage(100, 25, 125, 40), "test-model", "req-fixture"
    )

    def complete(system_prompt, user_prompt, *, agent):
        if error:
            raise error
        return response

    return SimpleNamespace(
        provider="test-provider", model="test-model", max_tokens=256, complete=complete
    )


def test_cost_uses_separate_input_output_and_cached_rates(billing_setup):
    price = load_active_price()
    assert calculate_cost(100, 25, price, tokens_cached=40) == Decimal("0.001180")
    assert calculate_cost(1000, 1000, Price(Decimal("1"), Decimal("3"))) == Decimal("4.000000")


def test_price_missing_never_invents_a_default(billing_setup):
    user, _ = billing_setup
    PricePlan.objects.all().delete()
    called = []
    inner = fake_inner()
    inner.complete = lambda *args, **kwargs: called.append(True)
    with pytest.raises(BillingError, match="PRICE_NOT_CONFIGURED"):
        MeteredLLM(inner, user=user).complete("system", "prompt", agent="explainer")
    assert called == []
    assert not UsageRecord.objects.exists()


def test_budget_missing_prevents_provider_call(billing_setup, settings):
    user, _ = billing_setup
    settings.DAILY_COST_BUDGET_PER_USER = ""
    with pytest.raises(BillingError, match="BUDGET_NOT_CONFIGURED"):
        MeteredLLM(fake_inner(), user=user).complete("s", "u", agent="explainer")


def test_wrapper_records_provider_usage_and_price_snapshot(billing_setup):
    user, plan = billing_setup
    result = MeteredLLM(
        fake_inner(), user=user, trace_id="trace-fixture", run_id="run-fixture"
    ).complete("s", "u", agent="explainer")
    assert result.content == "fixture response"
    row = UsageRecord.objects.get()
    assert (row.tokens_in, row.tokens_out, row.tokens_cached) == (100, 25, 40)
    assert row.cost == Decimal("0.001180")
    assert row.price_snapshot["plan_id"] == plan.pk
    assert row.trace_id == "trace-fixture"
    assert row.measurement == "provider"
    plan.input_per_1k = Decimal("9")
    plan.save()
    row.refresh_from_db()
    assert row.price_snapshot["input_per_1k"] == "0.010000"
    budget = DailyBudget.objects.get()
    assert budget.tokens_used == 125
    assert budget.cost == row.cost
    assert budget.cost_reserved == 0
    assert budget.tokens_reserved == 0


def test_unknown_usage_is_explicit_estimate_not_fake_provider_usage(billing_setup):
    user, _ = billing_setup
    MeteredLLM(fake_inner(usage=LLMUsage()), user=user).complete("s", "u", agent="safety")
    row = UsageRecord.objects.get()
    assert row.measurement == "estimated"
    assert row.tokens_out == 256


@pytest.mark.parametrize("code", ["RATE_LIMITED", "LLM_HTTP_400", "LLM_HTTP_401", None])
def test_definite_failure_releases_reservation_and_records_scoped_failure(billing_setup, code):
    from apps.monitoring.models import FailureEvent

    user, _ = billing_setup
    error = BillingError(code) if code else RuntimeError("fixture unsent failure")
    with pytest.raises(type(error)):
        MeteredLLM(fake_inner(error=error), user=user, run_id="run-failed").complete(
            "s", "u", agent="safety"
        )
    budget = DailyBudget.objects.get()
    assert (budget.tokens_reserved, budget.cost_reserved, budget.cost) == (0, 0, 0)
    assert UsageReservation.objects.get().status == "released"
    assert not UsageRecord.objects.exists()
    event = FailureEvent.objects.get()
    assert event.user_id == user.pk
    assert event.message == (code or "LLM_CALL_FAILED")
    assert event.payload == {}


@pytest.mark.parametrize(
    "code",
    [
        "TIMEOUT",
        "LLM_CONNECTION_ERROR",
        "LLM_PROVIDER_UNAVAILABLE",
        "INVALID_PROVIDER_RESPONSE",
    ],
)
def test_uncertain_provider_outcome_retains_budget_until_reconciled(billing_setup, settings, code):
    from apps.monitoring.models import FailureEvent

    user, _ = billing_setup
    settings.DAILY_TOKEN_BUDGET_PER_USER = 500
    with pytest.raises(BillingError, match=code):
        MeteredLLM(fake_inner(error=BillingError(code)), user=user).complete(
            "s", "u", agent="safety"
        )
    reservation = UsageReservation.objects.get()
    assert reservation.status == "reserved"
    budget = DailyBudget.objects.get()
    assert budget.tokens_reserved == reservation.tokens
    assert budget.cost_reserved == reservation.cost
    assert not UsageRecord.objects.exists()
    failure = FailureEvent.objects.get()
    assert failure.message == code
    assert failure.payload["reservation_call_id"] == str(reservation.call_id)
    assert failure.payload["reservation_state"] == "held_for_reconciliation"
    # The unresolved external spend cannot be made available to the next call.
    with pytest.raises(BillingError, match="BUDGET_EXCEEDED"):
        reserve(user, reservation.tokens, reservation.cost)
    release(reservation.call_id)
    budget.refresh_from_db()
    assert budget.tokens_reserved == 0


def test_overlapping_reservations_cannot_exceed_daily_cap(billing_setup, settings):
    user, _ = billing_setup
    settings.DAILY_COST_BUDGET_PER_USER = "1"
    first = reserve(user, 10, Decimal("0.6"))
    with pytest.raises(BillingError, match="BUDGET_EXCEEDED"):
        reserve(user, 10, Decimal("0.5"))
    assert UsageReservation.objects.count() == 1
    release(first.call_id)
    second = reserve(user, 10, Decimal("0.5"))
    assert second.status == "reserved"


def test_token_cap_includes_reservations(billing_setup, settings):
    user, _ = billing_setup
    settings.DAILY_TOKEN_BUDGET_PER_USER = 10
    reserve(user, 6, Decimal("0.01"))
    with pytest.raises(BillingError, match="BUDGET_EXCEEDED"):
        reserve(user, 5, Decimal("0.01"))


def test_wrapper_budget_rejection_emits_budget_failure(billing_setup, settings):
    from apps.monitoring.models import FailureEvent

    user, _ = billing_setup
    settings.DAILY_TOKEN_BUDGET_PER_USER = 1
    with pytest.raises(BillingError, match="BUDGET_EXCEEDED"):
        MeteredLLM(fake_inner(), user=user).complete("s", "u", agent="explainer")
    event = FailureEvent.objects.get()
    assert event.user_id == user.pk
    assert event.kind == "budget"
    assert event.message == "BUDGET_EXCEEDED"


def test_settlement_and_release_are_idempotent(billing_setup):
    user, _ = billing_setup
    call_id = uuid.uuid4()
    reservation = reserve(user, 1000, Decimal("0.1"), call_id=call_id)
    assert reserve(user, 1000, Decimal("0.1"), call_id=call_id).call_id == reservation.call_id
    kwargs = {
        "tokens_in": 100,
        "tokens_out": 25,
        "price": load_active_price(),
        "provider": "test-provider",
        "model": "test-model",
    }
    first = settle(call_id, **kwargs)
    second = settle(call_id, **kwargs)
    release(call_id)
    assert first.pk == second.pk
    assert UsageRecord.objects.count() == 1
    assert DailyBudget.objects.get().tokens_used == 125
    assert DailyBudget.objects.get().tokens_reserved == 0


def test_released_reservation_cannot_be_settled(billing_setup):
    user, _ = billing_setup
    reservation = reserve(user, 1000, Decimal("0.1"))
    release(reservation.call_id)
    release(reservation.call_id)
    with pytest.raises(BillingError, match="RESERVATION_NOT_ACTIVE"):
        settle(
            reservation.call_id,
            tokens_in=100,
            tokens_out=25,
            price=load_active_price(),
            provider="test-provider",
            model="test-model",
        )


def test_billing_api_isolates_users_and_exposes_configuration(billing_setup, django_user_model):
    user, _ = billing_setup
    other = django_user_model.objects.create_user(username="someone-else")
    UsageRecord.objects.create(user=other, tokens_in=9999, tokens_out=9999, cost="9")
    client = client_for(user)
    payload = client.get("/api/v1/billing/usage/?scope=all").json()
    assert payload["records"] == 0
    assert payload["scope"] == "own"
    assert payload["by_user"] == []
    budget = client.get("/api/v1/billing/budget/").json()
    assert budget["configured"] is True
    assert budget["price_configured"] is True
    assert budget["cost_limit"] == "2"


def test_staff_can_group_usage_by_user(billing_setup):
    user, _ = billing_setup
    user.is_staff = True
    user.save()
    UsageRecord.objects.create(user=user, tokens_in=12, tokens_out=7, cost="0.1")
    payload = client_for(user).get("/api/v1/billing/usage/?scope=all").json()
    assert payload["by_user"][0]["tokens"] == 19
    assert Decimal(payload["by_day"][0]["cost"]) == Decimal("0.1")


def test_same_consultation_has_separate_per_query_bills(billing_setup):
    from apps.consultations.models import Consultation

    user, _ = billing_setup
    consultation = Consultation.objects.create(user=user, title="多轮计费测试")
    first_run, second_run = str(uuid.uuid4()), str(uuid.uuid4())
    for run_id, agent, tokens_in, tokens_out, cost in [
        (first_run, "explainer", 100, 20, "0.01"),
        (first_run, "safety", 50, 10, "0.02"),
        (second_run, "explainer", 200, 40, "0.04"),
    ]:
        UsageRecord.objects.create(
            user=user,
            consultation=consultation,
            run_id=run_id,
            agent=agent,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
        )
    UsageRecord.objects.create(
        user=user,
        consultation=consultation,
        tokens_in=1,
        cost="0.001",
        measurement="legacy",
    )
    payload = client_for(user).get("/api/v1/billing/usage/").json()
    by_run = {item["run_id"]: item for item in payload["by_run"]}
    assert len(by_run) == 2
    assert by_run[first_run]["consultation_id"] == consultation.pk
    assert by_run[first_run]["tokens"] == 180
    assert Decimal(by_run[first_run]["cost"]) == Decimal("0.03")
    assert by_run[second_run]["tokens"] == 240
    assert Decimal(by_run[second_run]["cost"]) == Decimal("0.04")
    assert len(payload["by_query"]) == 1
    assert payload["by_query"][0]["tokens"] == 421
    assert Decimal(payload["by_query"][0]["cost"]) == Decimal("0.071")


def test_aggregated_money_has_six_decimal_places_including_empty_totals(billing_setup):
    user, _ = billing_setup
    user.is_staff = True
    user.save()
    client = client_for(user)
    empty = client.get("/api/v1/billing/usage/").json()
    assert empty["today"]["cost"] == "0.000000"
    assert empty["total"]["cost"] == "0.000000"
    budget = client.get("/api/v1/billing/budget/").json()
    assert budget["cost"] == "0.000000"
    assert budget["reserved_cost"] == "0.000000"
    assert budget["cost_limit"] == "2"
    for amount in ["0.010001", "0.010002", "0.006079"]:
        UsageRecord.objects.create(user=user, run_id="same-run", cost=amount)
    payload = client.get("/api/v1/billing/usage/?scope=all").json()
    assert payload["today"]["cost"] == "0.026082"
    assert payload["total"]["cost"] == "0.026082"
    for group in ["by_day", "by_query", "by_run", "by_user"]:
        assert payload[group][0]["cost"] == "0.026082"
    assert {item["cost"] for item in payload["latest"]} == {"0.010001", "0.010002", "0.006079"}


def test_settlement_failure_retains_reservation_for_reconciliation(billing_setup, monkeypatch):
    from apps.monitoring.models import FailureEvent

    user, _ = billing_setup

    def fail_settlement(*args, **kwargs):
        raise RuntimeError("fixture settlement failure")

    monkeypatch.setattr("apps.billing.services.metering.settle", fail_settlement)
    with pytest.raises(RuntimeError, match="fixture settlement failure"):
        MeteredLLM(fake_inner(), user=user).complete("s", "u", agent="explainer")
    reservation = UsageReservation.objects.get()
    assert reservation.status == "reserved"
    budget = DailyBudget.objects.get()
    assert budget.tokens_reserved == reservation.tokens
    assert budget.cost_reserved == reservation.cost
    assert not UsageRecord.objects.exists()
    assert FailureEvent.objects.get().message == "USAGE_SETTLEMENT_FAILED"


@pytest.mark.parametrize("values", [(-1, 1), (True, 1), (1, -1)])
def test_invalid_usage_rejected(values):
    with pytest.raises(BillingError, match="INVALID_USAGE"):
        calculate_cost(*values, Price(Decimal("1"), Decimal("1")))
