from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.agents.models import AgentRun
from apps.consultations.models import Consultation
from apps.monitoring.models import FailureEvent, Metric
from apps.monitoring.services import percentile_99, record_metric

pytestmark = pytest.mark.django_db


def logged_in(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_empty_metrics_are_not_fabricated_as_zero(django_user_model):
    user = django_user_model.objects.create_user(username="monitor-empty")
    payload = logged_in(user).get("/api/v1/monitoring/overview/").json()
    assert payload["retrieval"]["status"] == "not_connected"
    assert payload["retrieval"]["p99_latency_ms"] is None
    assert payload["knowledge"]["documents"] is None
    assert payload["feedback"]["positive_rate"] is None


def test_monitoring_regular_user_does_not_see_other_users(django_user_model):
    user = django_user_model.objects.create_user(username="monitor-one")
    other = django_user_model.objects.create_user(username="monitor-two")
    consultation = Consultation.objects.create(user=other)
    AgentRun.objects.create(consultation=consultation, agent_name="safety", status="failed")
    FailureEvent.objects.create(user=other, kind="timeout")
    Metric.objects.create(user=other, name="retrieval.latency_ms", value=500)
    payload = logged_in(user).get("/api/v1/monitoring/overview/?scope=all").json()
    assert payload["scope"] == "own"
    assert payload["agents"]["total"] == 0
    assert payload["failures"] == 0
    assert payload["retrieval"]["status"] == "not_connected"


def test_retrieval_metrics_aggregate_real_samples(django_user_model):
    user = django_user_model.objects.create_user(username="monitor-metrics")
    for index in range(1, 101):
        record_metric("retrieval.latency_ms", index, user=user)
        record_metric("retrieval.hit_count", index % 2, user=user)
    payload = logged_in(user).get("/api/v1/monitoring/overview/").json()
    assert payload["retrieval"]["status"] == "connected"
    assert payload["retrieval"]["avg_latency_ms"] == 50.5
    assert payload["retrieval"]["p99_latency_ms"] == 99
    assert payload["retrieval"]["no_hit_rate"] == 0.5


def test_telemetry_idempotency(django_user_model):
    user = django_user_model.objects.create_user(username="monitor-idempotent")
    first = record_metric("retrieval.latency_ms", 8, user=user, event_id="same-event")
    second = record_metric("retrieval.latency_ms", 8, user=user, event_id="same-event")
    assert first.pk == second.pk
    assert Metric.objects.count() == 1


def test_p99_uses_observed_sample():
    assert percentile_99([]) is None
    assert percentile_99([3]) == 3
    assert percentile_99(list(range(1, 101))) == 99
