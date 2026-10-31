from django.contrib import admin

from apps.billing.models import DailyBudget, PricePlan, UsageRecord


@admin.register(PricePlan)
class PricePlanAdmin(admin.ModelAdmin):
    list_display = ("name", "input_per_1k", "output_per_1k", "currency", "is_active")


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "model", "tokens_in", "tokens_out", "cost", "created_at")
    list_filter = ("provider", "model")


@admin.register(DailyBudget)
class DailyBudgetAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "tokens_used", "cost")
