from __future__ import annotations

from rest_framework import serializers

from apps.consultations.models import Consultation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id", "role", "content", "agent_name", "citations",
            "tokens_in", "tokens_out", "latency_ms", "created_at",
        )
        read_only_fields = fields


class ConsultationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consultation
        fields = ("id", "title", "status", "risk_level", "created_at", "updated_at")
        read_only_fields = ("id", "status", "risk_level", "created_at", "updated_at")


class ConsultationDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Consultation
        fields = (
            "id", "title", "status", "risk_level", "chief_complaint",
            "summary", "trace_id", "created_at", "updated_at", "messages",
        )
        read_only_fields = fields
