from django.contrib import admin

from apps.monitoring.models import FailureEvent, Metric


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ("name", "value", "recorded_at")
    list_filter = ("name",)


@admin.register(FailureEvent)
class FailureEventAdmin(admin.ModelAdmin):
    list_display = ("kind", "source", "created_at")
    list_filter = ("kind",)
