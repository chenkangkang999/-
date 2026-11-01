from django.urls import path

from apps.consultations.views import (
    ConsultationDetailView,
    ConsultationListCreateView,
    FeedbackView,
    MessageCreateView,
    RunDetailView,
    RunListCreateView,
)

urlpatterns = [
    path("", ConsultationListCreateView.as_view(), name="consultation-list"),
    path("<int:pk>/", ConsultationDetailView.as_view(), name="consultation-detail"),
    path("<int:pk>/messages/", MessageCreateView.as_view(), name="consultation-message"),
    path("<int:pk>/runs/", RunListCreateView.as_view(), name="consultation-runs"),
    path("<int:pk>/runs/<uuid:run_id>/", RunDetailView.as_view(), name="consultation-run"),
    path("<int:pk>/feedback/", FeedbackView.as_view(), name="consultation-feedback"),
]
