from django.contrib import admin

from apps.consultations.models import Consultation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "risk_level", "updated_at")
    list_filter = ("status", "risk_level")
    search_fields = ("user__username", "chief_complaint", "title")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "consultation", "role", "agent_name", "created_at")
    list_filter = ("role", "agent_name")
