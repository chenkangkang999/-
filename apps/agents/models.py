"""Agent 运行与步骤：监控面板、调用链追踪、计费都从这两张表取数。"""
from __future__ import annotations

from django.db import models


class AgentRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "运行中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"
        BLOCKED = "blocked", "被拦截"

    consultation = models.ForeignKey(
        "consultations.Consultation", null=True, blank=True,
        on_delete=models.CASCADE, related_name="agent_runs",
    )
    agent_name = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    trace_id = models.CharField(max_length=64, blank=True, db_index=True)
    input_payload = models.JSONField(default=dict, blank=True)
    output_payload = models.JSONField(default=dict, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_agent_run"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["agent_name", "-created_at"]),
            models.Index(fields=["trace_id"]),
        ]
        verbose_name = verbose_name_plural = "Agent 运行"

    def __str__(self) -> str:
        return f"{self.agent_name}@{self.created_at:%H:%M:%S}"


class AgentStep(models.Model):
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
    seq = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agents_agent_step"
        ordering = ("run", "seq")
        verbose_name = verbose_name_plural = "Agent 步骤"
