from __future__ import annotations

from django.urls import path

from apps.monitoring.views import OverviewView

urlpatterns = [path("overview/", OverviewView.as_view(), name="monitoring-overview")]
