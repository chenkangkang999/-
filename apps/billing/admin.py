from django.contrib import admin

from apps.billing.models import DailyBudget, PricePlan, UsageRecord, UsageReservation


@admin.register(PricePlan)
class PricePlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "provider",
        "model",
        "input_per_1k",
        "output_per_1k",
        "currency",
        "is_active",
    )
    list_filter = ("provider", "is_active", "currency")


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "agent",
        "model",
        "tokens_in",
        "tokens_out",
        "cost",
        "measurement",
        "created_at",
    )
    list_filter = ("provider", "model")
    readonly_fields = tuple(field.name for field in UsageRecord._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailyBudget)
class DailyBudgetAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "tokens_used", "cost", "tokens_reserved", "cost_reserved")
    readonly_fields = tuple(field.name for field in DailyBudget._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UsageReservation)
class UsageReservationAdmin(admin.ModelAdmin):
    list_display = ("call_id", "budget", "status", "tokens", "cost", "created_at")
    readonly_fields = tuple(field.name for field in UsageReservation._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
