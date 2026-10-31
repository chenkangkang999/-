from __future__ import annotations

from django.db.models import Avg, Count, Max
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.models import AgentRun
from apps.monitoring.models import FailureEvent
from apps.rag.models import Chunk, Document


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        latency = AgentRun.objects.aggregate(avg=Avg("latency_ms"), max=Max("latency_ms"))
        return Response(
            {
                "agents": AgentRun.objects.aggregate(
                    total=Count("id"), failed=Count("id", filter=models_failed())
                ),
                "latency_ms": {"avg": latency["avg"] or 0, "max": latency["max"] or 0},
                "knowledge": {
                    "documents": Document.objects.count(),
                    "chunks": Chunk.objects.count(),
                },
                "failures": FailureEvent.objects.count(),
            }
        )


def models_failed():
    from django.db.models import Q

    return Q(status=AgentRun.Status.FAILED)
