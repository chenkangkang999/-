from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.base.registry import list_agents, load_all
from apps.agents.models import AgentRun
from apps.agents.serializers import AgentRunSerializer


class AgentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        load_all()
        return Response({"agents": list_agents(), "debate_enabled": settings.ENABLE_DEBATE})


class AgentRunListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AgentRun.objects.filter(consultation__user=request.user)[:50]
        return Response({"results": AgentRunSerializer(qs, many=True).data})
