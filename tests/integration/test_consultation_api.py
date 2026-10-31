from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_create_consultation_and_send_message(auth_client):
    created = auth_client.post("/api/v1/consultations/", {"title": "咳嗽"}, format="json")
    assert created.status_code == 201
    consultation_id = created.json()["id"]

    reply = auth_client.post(
        f"/api/v1/consultations/{consultation_id}/messages/",
        {"content": "咳嗽三天，夜间加重"},
        format="json",
    )
    assert reply.status_code == 201
    payload = reply.json()
    assert payload["reply"]["role"] == "assistant"
    assert payload["reply"]["content"]
