from __future__ import annotations

import math

from rest_framework import serializers

from apps.consultations.models import Consultation, Message


class IntakeSubmissionSerializer(serializers.Serializer):
    def validate(self, attrs):
        if any(isinstance(value, float) and not math.isfinite(value) for value in attrs.values()):
            raise serializers.ValidationError("生命体征和检查数值必须是有限数值")
        return attrs

    def get_fields(self):
        from apps.consultations.services.clinical_schema import input_schema
        fields = super().get_fields()
        for item in input_schema()["fields"]:
            if item["type"] == "number":
                field = serializers.FloatField(required=False, min_value=item["min"], max_value=item["max"])
            elif item["type"] == "boolean":
                field = serializers.BooleanField(required=False)
            else:
                field = serializers.ChoiceField(required=False, choices=[o["value"] for o in item["options"]])
            fields[item["id"]] = field
        return fields

    age = serializers.CharField(required=False, allow_blank=True, max_length=500)
    duration = serializers.CharField(required=False, allow_blank=True, max_length=500)
    allergies = serializers.CharField(required=False, allow_blank=True, max_length=500)
    current_medications = serializers.CharField(required=False, allow_blank=True, max_length=500)
    chronic_conditions = serializers.CharField(required=False, allow_blank=True, max_length=500)
    associated_symptoms = serializers.CharField(required=False, allow_blank=True, max_length=500)


class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False, trim_whitespace=True, max_length=20000)
    intake = IntakeSubmissionSerializer(required=False)


class RunCreateSerializer(MessageCreateSerializer):
    client_request_id = serializers.UUIDField()


class FeedbackSerializer(serializers.Serializer):
    run_id = serializers.UUIDField()
    rating = serializers.ChoiceField(choices=[1, -1])
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    training_consent = serializers.BooleanField(required=False, default=False)


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id",
            "role",
            "content",
            "agent_name",
            "citations",
            "tokens_in",
            "tokens_out",
            "latency_ms",
            "created_at",
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
            "id",
            "title",
            "status",
            "risk_level",
            "chief_complaint",
            "summary",
            "trace_id",
            "created_at",
            "updated_at",
            "messages",
        )
        read_only_fields = fields
