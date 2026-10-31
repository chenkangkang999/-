from __future__ import annotations

from django.urls import path

from apps.rag.views import IndexStatusView, SearchView

urlpatterns = [
    path("search/", SearchView.as_view(), name="rag-search"),
    path("index/status/", IndexStatusView.as_view(), name="rag-index-status"),
]
