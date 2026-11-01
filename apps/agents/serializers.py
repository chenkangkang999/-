from __future__ import annotations

from rest_framework import serializers

from apps.agents.models import AgentRun


class AgentRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentRun
        fields = (
            "id",
            "agent_name",
            "status",
            "trace_id",
            "latency_ms",
            "tokens_in",
            "tokens_out",
            "cost",
            "created_at",
        )
        read_only_fields = fields
