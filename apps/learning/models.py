from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class DatasetAsset(models.Model):
    key = models.SlugField(unique=True)
    title = models.CharField(max_length=160)
    source = models.CharField(max_length=160)
    path = models.CharField(max_length=500)
    format = models.CharField(max_length=30)
    reported_rows = models.PositiveIntegerField(null=True)
    observed_rows = models.PositiveIntegerField(null=True)
    file_status = models.CharField(max_length=20, default="missing")
    bytes = models.PositiveBigIntegerField(null=True)
    sha256 = models.CharField(max_length=64, blank=True)
    provenance = models.CharField(max_length=30, default="document_reported")
    checked_at = models.DateTimeField(null=True)
    verified_mtime_ns = models.BigIntegerField(null=True)


class TrainingRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_key = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=160)
    status = models.CharField(max_length=30, default="unknown")
    phase = models.CharField(max_length=40, default="training")
    current_step = models.PositiveIntegerField(default=0)
    total_steps = models.PositiveIntegerField(null=True)
    epoch = models.FloatField(null=True)
    metrics = models.JSONField(default=dict)
    config = models.JSONField(default=dict)
    provenance = models.JSONField(default=dict)
    source = models.CharField(max_length=500, blank=True)
    artifact_path = models.CharField(max_length=1000, blank=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)


class TrainingEvent(models.Model):
    run = models.ForeignKey(TrainingRun, on_delete=models.CASCADE, related_name="events")
    fingerprint = models.CharField(max_length=64)
    kind = models.CharField(max_length=40, default="metric")
    phase = models.CharField(max_length=40, default="training")
    level = models.CharField(max_length=20, default="info")
    message = models.CharField(max_length=2000, blank=True)
    step = models.PositiveIntegerField(null=True)
    metrics = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "fingerprint"], name="learning_unique_event")
        ]
        ordering = ["id"]


class EvaluationReport(models.Model):
    run = models.ForeignKey(
        TrainingRun, null=True, on_delete=models.SET_NULL, related_name="evaluations"
    )
    source_key = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=160)
    source = models.CharField(max_length=30)
    verified = models.BooleanField(default=False)
    scope = models.JSONField(default=dict)
    metrics = models.JSONField(default=list)
    selected_model = models.CharField(max_length=80, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    artifacts = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class FlywheelCandidate(models.Model):
    feedback = models.OneToOneField(
        "consultations.Feedback", on_delete=models.CASCADE, related_name="learning_candidate"
    )
    status = models.CharField(max_length=24, default="pending")
    query = models.TextField()
    query_hash = models.CharField(max_length=64, db_index=True)
    comment = models.TextField(blank=True)
    citations = models.JSONField(default=list)
    positive = models.TextField(blank=True)
    negative = models.TextField(blank=True)
    positive_source = models.CharField(max_length=500, blank=True)
    negative_source = models.CharField(max_length=500, blank=True)
    review_note = models.TextField(blank=True)
    fingerprint = models.CharField(max_length=64, unique=True, null=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True)
    feedback_version = models.DateTimeField()
    redacted = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class FlywheelBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(max_length=160)
    status = models.CharField(max_length=30, default="frozen")
    records = models.JSONField(default=list)
    manifest = models.JSONField(default=dict)
    sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    training_run = models.OneToOneField(TrainingRun, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class ModelVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(TrainingRun, on_delete=models.PROTECT)
    label = models.CharField(max_length=160)
    adapter_path = models.CharField(max_length=1000)
    sha256 = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=False)
    validation_status = models.CharField(max_length=30, default="unverified")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="one_active_learning_model",
            )
        ]


class ModelActivation(models.Model):
    version = models.ForeignKey(
        ModelVersion, null=True, on_delete=models.PROTECT, related_name="activations"
    )
    previous = models.ForeignKey(
        ModelVersion, null=True, on_delete=models.PROTECT, related_name="replacements"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    review_note = models.CharField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
