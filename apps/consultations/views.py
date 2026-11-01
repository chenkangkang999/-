"""Authenticated consultation and durable run APIs."""

from __future__ import annotations

import uuid

from django.db import transaction
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.models import AgentRun
from apps.common.throttling import ConsultationTokenBucket
from apps.consultations.models import Consultation, ConsultationRun, Feedback
from apps.consultations.serializers import (
    ConsultationDetailSerializer,
    ConsultationListSerializer,
    FeedbackSerializer,
    MessageCreateSerializer,
    MessageSerializer,
    RunCreateSerializer,
)
from apps.consultations.services.coordinator import (
    ActiveRunError,
    IdempotencyConflict,
    create_run,
    dispatch_run,
    execute_run,
)


def owned_consultation(user, pk):
    try:
        return Consultation.objects.get(pk=pk, user=user)
    except Consultation.DoesNotExist:
        raise NotFound() from None


def serialize_run(run):
    steps = AgentRun.objects.filter(
        consultation_id=run.consultation_id, trace_id=run.trace_id
    ).order_by("id")
    return {
        "run_id": str(run.pk),
        "trace_id": run.trace_id,
        "status": run.status,
        "error": run.error,
        "message": MessageSerializer(run.message).data,
        "reply": MessageSerializer(run.reply).data if run.reply_id else None,
        "steps": [
            {
                "agent": s.agent_name,
                "status": "skipped" if s.output_payload.get("metadata", {}).get("status") == "skipped" else s.status,
                "latency_ms": s.latency_ms,
                "error_code": s.error or None,
            }
            for s in steps
        ],
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "metadata": run.metadata,
        "feedback": run.feedback.filter(user_id=run.consultation.user_id).values(
            "id", "rating", "comment", "training_consent"
        ).first(),
        **run.metadata,
    }


class ConsultationListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConsultationListSerializer

    def get_queryset(self):
        return Consultation.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ConsultationDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConsultationDetailSerializer

    def get_queryset(self):
        return Consultation.objects.filter(user=self.request.user)


class MessageCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ConsultationTokenBucket]

    def post(self, request, pk):
        consultation = owned_consultation(request.user, pk)
        payload = MessageCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            run, _ = create_run(consultation, payload.validated_data["content"], uuid.uuid4(),
                                intake=payload.validated_data.get("intake"))
        except ActiveRunError as exc:
            return Response({"detail": str(exc), "code": "RUN_ACTIVE"}, status=409)
        execute_run(run.pk)
        run.refresh_from_db()
        data = serialize_run(run)
        if run.status == "failed":
            return Response(data, status=503)
        return Response({**data, "message": MessageSerializer(run.message).data}, status=201)


class RunListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ConsultationTokenBucket]

    def get(self, request, pk):
        consultation = owned_consultation(request.user, pk)
        runs = consultation.runs.select_related("message", "reply")[:50]
        return Response({"results": [serialize_run(run) for run in runs]})

    def post(self, request, pk):
        consultation = owned_consultation(request.user, pk)
        data = RunCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            run, created = create_run(
                consultation,
                data.validated_data["content"],
                data.validated_data["client_request_id"],
                intake=data.validated_data.get("intake"),
            )
        except (ActiveRunError, IdempotencyConflict) as exc:
            return Response({"detail": str(exc), "code": "RUN_CONFLICT"}, status=409)
        if created:
            try:
                transaction.on_commit(lambda: dispatch_run(run))
            except Exception:
                from django.utils import timezone

                ConsultationRun.objects.filter(pk=run.pk).update(
                    status="failed",
                    finished_at=timezone.now(),
                    error={
                        "code": "QUEUE_UNAVAILABLE",
                        "message": "运行队列不可用，请联系管理员。",
                    },
                )
        run.refresh_from_db()
        return Response(serialize_run(run), status=202 if created else 200)


class RunDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, run_id):
        consultation = owned_consultation(request.user, pk)
        run = consultation.runs.select_related("message", "reply").filter(pk=run_id).first()
        if run is None:
            raise NotFound()
        return Response(serialize_run(run))


class FeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        consultation = owned_consultation(request.user, pk)
        data = FeedbackSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        run = consultation.runs.filter(pk=data.validated_data["run_id"]).first()
        if run is None:
            raise NotFound()
        if run.status not in {"succeeded", "blocked"}:
            raise ValidationError({"detail": "只能对已经完成的回复提交反馈"})
        values = {"consultation": consultation, "rating": data.validated_data["rating"], "comment": data.validated_data.get("comment", ""), "training_consent": data.validated_data["training_consent"]}
        with transaction.atomic():
            feedback, created = Feedback.objects.select_for_update().get_or_create(user=request.user, run=run, defaults=values)
            if not created and any(getattr(feedback, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(feedback, key, value)
                feedback.save(update_fields=[*values, "updated_at"])
        from apps.learning.flywheel import refresh_feedback

        refresh_feedback(feedback)
        return Response({"id": feedback.pk, "rating": feedback.rating, "run_id": str(run.pk), "training_consent": feedback.training_consent})
