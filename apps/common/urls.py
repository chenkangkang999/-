from __future__ import annotations

from django.urls import path

from apps.common.views import health

urlpatterns = [path("health/", health, name="api-health")]
