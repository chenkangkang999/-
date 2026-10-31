from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_health_endpoint(api_client, db):
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
