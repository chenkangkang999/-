from django.contrib import admin

from apps.agents.models import AgentRun, AgentStep


class StepInline(admin.TabularInline):
    model = AgentStep
    extra = 0


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ("agent_name", "status", "latency_ms", "tokens_in", "tokens_out", "created_at")
    list_filter = ("status", "agent_name")
    search_fields = ("trace_id",)
    inlines = [StepInline]
