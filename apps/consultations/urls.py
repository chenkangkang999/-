from __future__ import annotations

from django.urls import path

from apps.consultations.views import (
    ConsultationDetailView,
    ConsultationListCreateView,
    MessageCreateView,
)

urlpatterns = [
    path("", ConsultationListCreateView.as_view(), name="consultation-list"),
    path("<int:pk>/", ConsultationDetailView.as_view(), name="consultation-detail"),
    path("<int:pk>/messages/", MessageCreateView.as_view(), name="consultation-message"),
]
