from __future__ import annotations

from django.urls import path

from apps.agents.views import AgentListView, AgentRunListView, AgentTestView

urlpatterns = [
    path("<str:name>/test/", AgentTestView.as_view(), name="agent-test"),
    path("", AgentListView.as_view(), name="agent-list"),
    path("runs/", AgentRunListView.as_view(), name="agent-runs"),
]
