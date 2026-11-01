from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.consultations.models import Consultation, ConsultationRun, Feedback, Message
from apps.consultations.services.coordinator import WebContext

pytestmark = pytest.mark.django_db


def install_provider(monkeypatch, decision="pass", safety_error=False):
    import apps.consultations.services.coordinator as service

    def prepare(run):
        return WebContext(
            consultation_id=run.consultation_id,
            user_id=run.consultation.user_id,
            trace_id=run.trace_id,
        ).configure(run)

    class Provider:
        def run(self, text, context, enable_debate=True):
            context.record(
                "explainer",
                {
                    "content": "UNREVIEWED_CANDIDATE",
                    "metadata": {},
                    "latency_ms": 3,
                    "citations": [],
                },
            )
            if decision is not None:
                context.record(
                    "safety",
                    {
                        "content": "IGNORE_THIS_FIELD",
                        "metadata": {
                            "decision": decision,
                            "approved_text": "已审核回复，不替代医生。",
                            "severity": "low",
                            "risk_level": "low",
                        },
                        "error": "TIMEOUT" if safety_error else None,
                    },
                )
            return SimpleNamespace(
                reply="UNREVIEWED_CANDIDATE", steps=context.steps, risk_level="low"
            )

    monkeypatch.setattr(service, "_prepare_context", prepare)
    monkeypatch.setattr(service, "import_string", lambda path: Provider)


def create_consultation(client):
    response = client.post(
        "/api/v1/consultations/", {"title": "输入保存与安全发布测试"}, format="json"
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_original_input_is_saved_and_only_approved_text_published(auth_client, monkeypatch):
    install_provider(monkeypatch)
    cid = create_consultation(auth_client)
    with patch("apps.consultations.services.coordinator.publish") as events:
        response = auth_client.post(
            f"/api/v1/consultations/{cid}/messages/",
            {"content": "咳嗽三天，夜间加重"},
            format="json",
        )
    assert response.status_code == 201
    assert response.json()["message"]["content"] == "咳嗽三天，夜间加重"
    assert response.json()["reply"]["content"] == "已审核回复，不替代医生。"
    assert not Message.objects.filter(content__contains="UNREVIEWED").exists()
    assert "UNREVIEWED" not in str(list(Consultation.objects.values()))
    assert "UNREVIEWED" not in str([call.kwargs for call in events.call_args_list])


@pytest.mark.parametrize(
    "decision,safety_error", [(None, False), ("pass", True), ("invalid", False)]
)
def test_safety_failure_never_publishes_candidate(auth_client, monkeypatch, decision, safety_error):
    install_provider(monkeypatch, decision, safety_error)
    cid = create_consultation(auth_client)
    with patch("apps.consultations.services.coordinator.publish") as events:
        response = auth_client.post(
            f"/api/v1/consultations/{cid}/messages/",
            {"content": "一般症状"},
            format="json",
        )
    assert response.status_code == 503
    assert response.json()["reply"] is None
    assert response.json()["error"]["code"] == ("TIMEOUT" if safety_error else "SAFETY_UNAVAILABLE")
    assert not Message.objects.filter(role="assistant").exists()
    assert all(c.kwargs["event_type"] != "answer.chunk" for c in events.call_args_list)


def test_block_uses_approved_replacement(auth_client, monkeypatch):
    install_provider(monkeypatch, "block")
    cid = create_consultation(auth_client)
    response = auth_client.post(
        f"/api/v1/consultations/{cid}/messages/", {"content": "需要开药"}, format="json"
    )
    assert response.status_code == 201
    assert response.json()["status"] == "blocked"
    assert response.json()["reply"]["content"] == "已审核回复，不替代医生。"


def test_runs_idempotency_and_active_conflict(auth_client):
    cid = create_consultation(auth_client)
    key = str(uuid.uuid4())
    url = f"/api/v1/consultations/{cid}/runs/"
    with patch("apps.consultations.views.dispatch_run"):
        with patch("apps.consultations.views.transaction.on_commit", side_effect=lambda fn: fn()):
            response = auth_client.post(
                url, {"content": "头痛一天", "client_request_id": key}, format="json"
            )
            duplicate = auth_client.post(
                url, {"content": "头痛一天", "client_request_id": key}, format="json"
            )
            conflict = auth_client.post(
                url, {"content": "不同内容", "client_request_id": key}, format="json"
            )
            concurrent = auth_client.post(
                url, {"content": "下一条", "client_request_id": str(uuid.uuid4())}, format="json"
            )
    assert response.status_code == 202
    assert duplicate.status_code == 200
    assert response.json()["run_id"] == duplicate.json()["run_id"]
    assert conflict.status_code == concurrent.status_code == 409
    assert Message.objects.filter(consultation_id=cid).count() == 1
    assert ConsultationRun.objects.count() == 1


def test_empty_input_rejected(auth_client):
    cid = create_consultation(auth_client)
    response = auth_client.post(
        f"/api/v1/consultations/{cid}/messages/", {"content": " "}, format="json"
    )
    assert response.status_code == 400
    assert not Message.objects.exists()


def test_run_and_feedback_owner_isolation(auth_client, user, monkeypatch):
    install_provider(monkeypatch)
    cid = create_consultation(auth_client)
    response = auth_client.post(
        f"/api/v1/consultations/{cid}/messages/", {"content": "咳嗽"}, format="json"
    )
    run_id = response.json()["run_id"]
    feedback_url = f"/api/v1/consultations/{cid}/feedback/"
    assert (
        auth_client.post(feedback_url, {"run_id": run_id, "rating": 1}, format="json").status_code
        == 200
    )
    assert (
        auth_client.post(feedback_url, {"run_id": run_id, "rating": -1}, format="json").status_code
        == 200
    )
    assert Feedback.objects.count() == 1
    other = get_user_model().objects.create_user(username="other", password="other-secure-password")
    auth_client.force_authenticate(user=other)
    assert auth_client.get(f"/api/v1/consultations/{cid}/runs/{run_id}/").status_code == 404
    assert (
        auth_client.post(feedback_url, {"run_id": run_id, "rating": 1}, format="json").status_code
        == 404
    )


def test_login_requires_csrf_and_logout_clears_session(user):
    client = APIClient(enforce_csrf_checks=True)
    credentials = {"username": "tester", "password": "pass-123456"}
    assert client.post("/api/v1/accounts/login/", credentials, format="json").status_code == 403
    token = client.get("/api/v1/accounts/csrf/").json()["csrf_token"]
    response = client.post(
        "/api/v1/accounts/login/", credentials, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200
    assert client.get("/api/v1/accounts/me/").json()["username"] == "tester"
    assert (
        client.post("/api/v1/consultations/", {"title": "missing csrf"}, format="json").status_code
        == 403
    )
    token = client.cookies["csrftoken"].value
    assert client.post("/api/v1/accounts/logout/", HTTP_X_CSRFTOKEN=token).status_code == 200
    assert client.get("/api/v1/accounts/me/").status_code == 403


def test_agent_test_restricted_to_staff(auth_client):
    assert (
        auth_client.post("/api/v1/agents/explainer/test/", {"content": "咳嗽"}).status_code == 403
    )


@pytest.mark.django_db(transaction=True)
def test_emergency_exit_remains_available_without_model_key(auth_client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    created = auth_client.post(
        "/api/v1/consultations/", {"title": "合成紧急风险出口"}, format="json"
    )
    cid = created.json()["id"]
    response = auth_client.post(
        f"/api/v1/consultations/{cid}/messages/",
        {"content": "合成测试：胸痛伴呼吸困难"},
        format="json",
    )
    assert response.status_code == 201
    assert "120" in response.json()["reply"]["content"]
    consultation = Consultation.objects.get(pk=cid)
    assert consultation.risk_level == "critical"
    assert consultation.status == "escalated"
