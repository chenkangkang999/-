from django.urls import path

from apps.learning import views

urlpatterns = [
    path("overview/", views.OverviewView.as_view()),
    path("datasets/", views.DatasetListView.as_view()),
    path("datasets/<slug:key>/preview/", views.DatasetPreviewView.as_view()),
    path("sync/", views.SyncView.as_view()),
    path("runs/", views.RunListView.as_view()),
    path("runs/<uuid:run_id>/", views.RunDetailView.as_view()),
    path("runs/<uuid:run_id>/events/", views.EventListView.as_view()),
    path("evaluations/", views.EvaluationListView.as_view()),
    path("models/", views.ModelListView.as_view()),
    path("models/register/", views.ModelRegisterView.as_view()),
    path("models/<uuid:version_id>/activate/", views.ModelActivateView.as_view()),
    path("models/rollback/", views.ModelRollbackView.as_view()),
    path("flywheel/overview/", views.FlywheelOverviewView.as_view()),
    path("flywheel/collect/", views.CollectView.as_view()),
    path("flywheel/candidates/", views.CandidateListView.as_view()),
    path("flywheel/candidates/<int:candidate_id>/review/", views.CandidateReviewView.as_view()),
    path("flywheel/batches/", views.BatchListView.as_view()),
    path("flywheel/batches/<uuid:batch_id>/download/", views.BatchDownloadView.as_view()),
    path("flywheel/batches/<uuid:batch_id>/prepare/", views.BatchPrepareView.as_view()),
]
