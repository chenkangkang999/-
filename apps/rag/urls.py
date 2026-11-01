from __future__ import annotations

from django.urls import path

from apps.rag.views import IndexStatusView, RAGStatusView, SearchView

urlpatterns = [
    path("status/", RAGStatusView.as_view(), name="rag-status"),
    path("search/", SearchView.as_view(), name="rag-search"),
    path("index/status/", IndexStatusView.as_view(), name="rag-index-status"),
]
