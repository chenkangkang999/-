from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_create_consultation_and_missing_llm_configuration_fails_explicitly(
    auth_client, monkeypatch
):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    created = auth_client.post("/api/v1/consultations/", {"title": "咳嗽"}, format="json")
    assert created.status_code == 201
    consultation_id = created.json()["id"]

    reply = auth_client.post(
        f"/api/v1/consultations/{consultation_id}/messages/",
        {"content": "咳嗽三天，夜间加重"},
        format="json",
    )
    assert reply.status_code == 503
    payload = reply.json()
    assert payload["message"]["content"] == "咳嗽三天，夜间加重"
    assert payload["reply"] is None
    assert payload["error"]["code"] == "LLM_NOT_CONFIGURED"
