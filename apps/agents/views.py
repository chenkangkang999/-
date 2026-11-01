from __future__ import annotations

import os
import uuid

from django.conf import settings
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.base.registry import list_agents, load_all
from apps.agents.models import AgentRun
from apps.agents.serializers import AgentRunSerializer
from apps.consultations.models import Consultation
from apps.consultations.serializers import MessageCreateSerializer
from apps.consultations.services.coordinator import create_run, execute_run
from apps.consultations.views import serialize_run


class AgentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        load_all()
        from apps.learning.models import ModelVersion
        from apps.rag.models import IndexRun
        history = "langchain" if settings.HISTORY_PROVIDER.endswith("LangChainHistory") else "database" if settings.HISTORY_PROVIDER.endswith("DatabaseHistory") else "external"
        return Response(
            {
                "agents": list_agents(),
                "debate_enabled": settings.ENABLE_DEBATE,
                "llm_configured": bool(
                    os.getenv("LLM_API_KEY")
                    and os.getenv("LLM_MODEL")
                    and os.getenv("LLM_BASE_URL")
                ),
                "history_provider": history,
                "integration_status": {
                    "base_agents": "implemented",
                    "retrieval": settings.RAG_MODE if IndexRun.objects.filter(status="succeeded", stats__mode=settings.RAG_MODE).exists() else "not_connected",
                    "lora": "registered" if ModelVersion.objects.filter(is_active=True).exists() else "not_connected",
                    "langchain_history": "connected" if history == "langchain" else "not_connected",
                },
            }
        )


class AgentRunListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AgentRun.objects.filter(consultation__user=request.user)
        if request.query_params.get("trace_id"):
            qs = qs.filter(trace_id=request.query_params["trace_id"])
        return Response({"results": AgentRunSerializer(qs[:100], many=True).data})


class AgentTestView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, name):
        load_all()
        if name not in {item["name"] for item in list_agents()}:
            return Response({"detail": "Agent 未注册"}, status=404)
        data = MessageCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        consultation = Consultation.objects.create(user=request.user, title=f"Agent 测试 · {name}")
        run, _ = create_run(consultation, data.validated_data["content"], uuid.uuid4())
        run.metadata = {"test_agent": name}
        run.save(update_fields=["metadata"])
        execute_run(run.pk)
        run.refresh_from_db()
        return Response(serialize_run(run), status=200 if run.status != "failed" else 503)
