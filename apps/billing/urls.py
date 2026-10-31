from __future__ import annotations

from django.urls import path

from apps.billing.views import BudgetView, UsageSummaryView

urlpatterns = [
    path("usage/", UsageSummaryView.as_view(), name="billing-usage"),
    path("budget/", BudgetView.as_view(), name="billing-budget"),
]
