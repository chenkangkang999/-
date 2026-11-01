from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.consultations.models import Feedback
from apps.learning import flywheel, registry, training
from apps.learning.models import (
    DatasetAsset,
    EvaluationReport,
    FlywheelBatch,
    FlywheelCandidate,
    ModelActivation,
    ModelVersion,
    TrainingEvent,
    TrainingRun,
)
from apps.learning.preview import PreviewThrottle, preview


class LearningView(APIView):
    permission_classes = [IsAdminUser]


class OverviewView(LearningView):
    def get(self, request):
        manifest = training.load_manifest()
        cfg = training.config()
        last = TrainingRun.objects.order_by("-updated_at").first()
        return Response(
            {
                "configuration": cfg,
                "sync_required": not DatasetAsset.objects.exists(),
                "selected_profile": {
                    **manifest.get("selected_profile", {}),
                    "parameters": cfg.get("train", {}),
                },
                "datasets": {
                    "total": DatasetAsset.objects.count(),
                    "verified": DatasetAsset.objects.filter(file_status="verified").count(),
                    "missing": DatasetAsset.objects.filter(file_status="missing").count(),
                },
                "training": {
                    "runs": TrainingRun.objects.count(),
                    "active": TrainingRun.objects.filter(status="running").count(),
                    "last_run": training.run_payload(last) if last else None,
                },
                "updated_at": timezone.now(),
            }
        )


class DatasetListView(LearningView):
    def get(self, request):
        return Response(
            {
                "results": [
                    training.dataset_payload(item) for item in DatasetAsset.objects.order_by("id")
                ]
            }
        )


class DatasetPreviewView(LearningView):
    throttle_classes = [PreviewThrottle]

    def get(self, request, key):
        if set(request.query_params) - {"limit"}:
            raise ValidationError("样例接口仅接受limit，不接受文件路径")
        asset = get_object_or_404(DatasetAsset, key=key)
        response = Response(preview(asset, request.query_params.get("limit", "3")))
        response["Cache-Control"] = "no-store"
        return response


class SyncView(LearningView):
    def post(self, request):
        if request.data:
            raise ValidationError("同步只读取服务端已配置目录，不接受客户端文件路径")
        return Response(training.synchronize())


class RunListView(LearningView):
    def get(self, request):
        return Response(
            {
                "results": [
                    training.run_payload(item)
                    for item in TrainingRun.objects.order_by("-updated_at")[:100]
                ]
            }
        )


class RunDetailView(LearningView):
    def get(self, request, run_id):
        return Response(training.run_payload(get_object_or_404(TrainingRun, pk=run_id)))


class EventListView(LearningView):
    def get(self, request, run_id):
        run = get_object_or_404(TrainingRun, pk=run_id)
        try:
            cursor = int(request.query_params.get("after", "0"))
            if cursor < 0:
                raise ValueError
        except ValueError:
            raise ValidationError("事件游标必须是非负整数") from None
        events = list(TrainingEvent.objects.filter(run=run, id__gt=cursor).order_by("id")[:200])
        return Response(
            {
                "results": [
                    {
                        key: getattr(event, key)
                        for key in (
                            "id",
                            "kind",
                            "phase",
                            "level",
                            "message",
                            "step",
                            "metrics",
                            "created_at",
                        )
                    }
                    for event in events
                ],
                "next_cursor": events[-1].id if events else cursor,
            }
        )


class EvaluationListView(LearningView):
    def get(self, request):
        return Response(
            {
                "results": [
                    training.evaluation_payload(item)
                    for item in EvaluationReport.objects.order_by("-verified", "-updated_at")[:100]
                ]
            }
        )


class FlywheelOverviewView(LearningView):
    def get(self, request):
        return Response(
            {
                "feedback_total": Feedback.objects.count(),
                "consented": Feedback.objects.filter(training_consent=True).count(),
                **{
                    status: FlywheelCandidate.objects.filter(status=status).count()
                    for status in ("pending", "approved", "rejected", "revoked")
                },
                "batches": FlywheelBatch.objects.count(),
                "training_requests": FlywheelBatch.objects.exclude(training_run=None).count(),
                "policy": {
                    "requires_consent": True,
                    "requires_review": True,
                    "automatic_training": False,
                },
            }
        )


class CollectView(LearningView):
    def post(self, request):
        result = flywheel.collect()
        return Response(
            {
                **result,
                "results": [
                    flywheel.candidate_payload(item)
                    for item in FlywheelCandidate.objects.select_related("feedback").order_by(
                        "-id"
                    )[:100]
                ],
            }
        )


class CandidateListView(LearningView):
    def get(self, request):
        return Response(
            {
                "results": [
                    flywheel.candidate_payload(item)
                    for item in FlywheelCandidate.objects.select_related("feedback").order_by(
                        "-id"
                    )[:200]
                ]
            }
        )


class CandidateReviewView(LearningView):
    def post(self, request, candidate_id):
        candidate = get_object_or_404(FlywheelCandidate, pk=candidate_id)
        return Response(
            flywheel.candidate_payload(flywheel.review(candidate, request.data, request.user))
        )


class BatchListView(LearningView):
    def get(self, request):
        return Response(
            {
                "results": [
                    flywheel.batch_payload(item)
                    for item in FlywheelBatch.objects.order_by("-created_at")[:100]
                ]
            }
        )

    def post(self, request):
        return Response(
            flywheel.batch_payload(flywheel.create_batch(request.data, request.user)), status=201
        )


class BatchDownloadView(LearningView):
    def get(self, request, batch_id):
        batch = get_object_or_404(FlywheelBatch, pk=batch_id)
        content = flywheel.export_rows(
            batch,
            request.query_params.get("format", "triplets"),
            request.query_params.get("split", "train"),
        )
        response = HttpResponse(content, content_type="application/x-ndjson; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="bge-feedback-{batch.pk}.jsonl"'
        response["Cache-Control"] = "no-store"
        return response


class BatchPrepareView(LearningView):
    def post(self, request, batch_id):
        return Response(flywheel.prepare(get_object_or_404(FlywheelBatch, pk=batch_id)))


class ModelListView(LearningView):
    def get(self, request):
        active = ModelVersion.objects.filter(is_active=True).first()
        return Response(
            {
                "results": [
                    registry.version_payload(item)
                    for item in ModelVersion.objects.order_by("-created_at")[:100]
                ],
                "activations": [
                    registry.activation_payload(item)
                    for item in ModelActivation.objects.order_by("-id")[:100]
                ],
                "active_id": str(active.pk) if active else None,
            }
        )


class ModelRegisterView(LearningView):
    def post(self, request):
        try:
            run = TrainingRun.objects.get(pk=request.data.get("run_id"))
        except (TrainingRun.DoesNotExist, ValueError, TypeError):
            raise ValidationError("训练运行不存在") from None
        if not isinstance(request.data.get("adapter_path"), str):
            raise ValidationError("请填写真实adapter目录")
        return Response(
            registry.version_payload(
                registry.register(run, request.data.get("label"), request.data["adapter_path"])
            ),
            status=201,
        )


class ModelActivateView(LearningView):
    def post(self, request, version_id):
        entry = registry.activate(
            get_object_or_404(ModelVersion, pk=version_id),
            request.user,
            request.data.get("review_note"),
            request.data.get("evidence_confirmed") is True,
        )
        return Response(registry.activation_payload(entry))


class ModelRollbackView(LearningView):
    def post(self, request):
        if not isinstance(request.data.get("activation_id"), int):
            raise ValidationError("请提供启用记录ID")
        entry = registry.rollback(
            get_object_or_404(ModelActivation, pk=request.data["activation_id"]),
            request.user,
            request.data.get("review_note"),
        )
        return Response(registry.activation_payload(entry))
