"""患者档案：把「对话历史」之外的稳定事实结构化存下来（长期记忆的基础）。"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class PatientProfile(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "female", "女"
        MALE = "male", "男"
        OTHER = "other", "其他"
        UNKNOWN = "unknown", "未填写"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    display_name = models.CharField("称呼", max_length=64, blank=True)
    birth_date = models.DateField("出生日期", null=True, blank=True)
    sex = models.CharField("性别", max_length=16, choices=Sex.choices, default=Sex.UNKNOWN)
    allergies = models.JSONField("过敏史", default=list, blank=True)
    chronic_conditions = models.JSONField("慢病", default=list, blank=True)
    current_medications = models.JSONField("在用药物", default=list, blank=True)
    consent_data_use = models.BooleanField("同意数据用于改进", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_patient_profile"
        verbose_name = verbose_name_plural = "患者档案"

    def __str__(self) -> str:
        return f"{self.display_name or self.user_id}"
