"""监控埋点：时序指标 + 失败事件。"""
from __future__ import annotations

from django.db import models


class Metric(models.Model):
    name = models.CharField(max_length=128, db_index=True)
    value = models.FloatField()
    labels = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "monitoring_metric"
        ordering = ("-recorded_at",)
        indexes = [models.Index(fields=["name", "-recorded_at"])]
        verbose_name = verbose_name_plural = "指标"


class FailureEvent(models.Model):
    class Kind(models.TextChoices):
        TIMEOUT = "timeout", "超时"
        RATE_LIMIT = "rate_limit", "限流"
        PARSE = "parse", "解析失败"
        BUDGET = "budget", "预算溢出"
        AGENT = "agent", "Agent 失败"
        OTHER = "other", "其他"

    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.OTHER)
    source = models.CharField(max_length=64, blank=True)
    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "monitoring_failure_event"
        ordering = ("-created_at",)
        verbose_name = verbose_name_plural = "失败事件"
