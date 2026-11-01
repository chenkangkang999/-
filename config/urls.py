"""URL 总入口：/api/v1/ 挂业务路由，/admin/ 管理后台。"""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from apps.common.views import health
from apps.consultations.clinical_views import ClinicalInputSchemaView

urlpatterns = [
    path("api/v1/clinical/schema/", ClinicalInputSchemaView.as_view()),
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/v1/", include("apps.common.urls")),
    path("api/v1/accounts/", include("apps.accounts.urls")),
    path("api/v1/consultations/", include("apps.consultations.urls")),
    path("api/v1/agents/", include("apps.agents.urls")),
    path("api/v1/rag/", include("apps.rag.urls")),
    path("api/v1/billing/", include("apps.billing.urls")),
    path("api/v1/monitoring/", include("apps.monitoring.urls")),
    path("api/v1/learning/", include("apps.learning.urls")),
]
