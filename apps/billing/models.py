"""计费模型：价格表 → 用量流水 → 每日预算。"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class PricePlan(models.Model):
    name = models.CharField(max_length=64, unique=True)
    input_per_1k = models.DecimalField("输入 元/千 token", max_digits=10, decimal_places=6)
    output_per_1k = models.DecimalField("输出 元/千 token", max_digits=10, decimal_places=6)
    currency = models.CharField(max_length=8, default="CNY")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_price_plan"
        verbose_name = verbose_name_plural = "价格方案"

    def __str__(self) -> str:
        return f"{self.name} ({self.currency})"


class UsageRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage_records"
    )
    consultation = models.ForeignKey(
        "consultations.Consultation", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="usage_records",
    )
    provider = models.CharField(max_length=32, default="openai")
    model = models.CharField(max_length=64, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "billing_usage_record"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]
        verbose_name = verbose_name_plural = "用量流水"


class DailyBudget(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_budgets"
    )
    date = models.DateField()
    tokens_used = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)

    class Meta:
        db_table = "billing_daily_budget"
        unique_together = ("user", "date")
        verbose_name = verbose_name_plural = "每日预算"
