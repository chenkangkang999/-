from django.contrib import admin

from apps.accounts.models import PatientProfile


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "sex", "updated_at")
    search_fields = ("user__username", "display_name")
