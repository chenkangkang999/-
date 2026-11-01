"""问诊会话与消息：整条多智能体链路的「事实表」。"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Consultation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "进行中"
        AWAITING_REVIEW = "awaiting_review", "待医生复核"
        CLOSED = "closed", "已结束"
        ESCALATED = "escalated", "已转急诊"

    class RiskLevel(models.TextChoices):
        UNKNOWN = "unknown", "尚不能评估"
        LOW = "low", "低"
        MEDIUM = "medium", "中"
        HIGH = "high", "高"
        CRITICAL = "critical", "极高"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consultations"
    )
    title = models.CharField("会话标题", max_length=128, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ACTIVE)
    risk_level = models.CharField(max_length=16, choices=RiskLevel.choices, default=RiskLevel.UNKNOWN)
    chief_complaint = models.TextField("主诉", blank=True)
    summary = models.TextField("SOAP 小结", blank=True)
    trace_id = models.CharField("调用链 id", max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "consultations_consultation"
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=["user", "-updated_at"])]
        verbose_name = verbose_name_plural = "问诊会话"

    def __str__(self) -> str:
        return f"#{self.pk} {self.title or self.chief_complaint[:20]}"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "用户"
        ASSISTANT = "assistant", "助手"
        SYSTEM = "system", "系统"

    consultation = models.ForeignKey(
        Consultation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    agent_name = models.CharField("产出该消息的 Agent", max_length=64, blank=True)
    citations = models.JSONField("引用证据", default=list, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "consultations_message"
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=["consultation", "created_at"])]
        verbose_name = verbose_name_plural = "问诊消息"

    def __str__(self) -> str:
        return f"{self.role}:{self.content[:20]}"


class ConsultationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "等待执行"
        RUNNING = "running", "运行中"
        SUCCEEDED = "succeeded", "已完成"
        BLOCKED = "blocked", "已安全拦截"
        FAILED = "failed", "执行失败"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name="runs")
    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="request_run")
    reply = models.OneToOneField(
        Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="response_run"
    )
    client_request_id = models.UUIDField()
    trace_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    error = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["consultation", "client_request_id"], name="unique_consultation_request"
            ),
            models.UniqueConstraint(
                fields=["consultation"],
                condition=models.Q(status__in=["pending", "running"]),
                name="one_active_consultation_run",
            ),
        ]


class Feedback(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    consultation = models.ForeignKey(
        Consultation, on_delete=models.CASCADE, related_name="feedback"
    )
    run = models.ForeignKey(ConsultationRun, on_delete=models.CASCADE, related_name="feedback")
    rating = models.SmallIntegerField(choices=[(1, "有帮助"), (-1, "需改进")])
    comment = models.CharField(max_length=2000, blank=True)
    training_consent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "run"], name="unique_run_feedback")]
