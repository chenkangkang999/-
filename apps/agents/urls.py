from __future__ import annotations

from django.urls import path

from apps.agents.views import AgentListView, AgentRunListView

urlpatterns = [
    path("", AgentListView.as_view(), name="agent-list"),
    path("runs/", AgentRunListView.as_view(), name="agent-runs"),
]
