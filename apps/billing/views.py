from __future__ import annotations

from django.db.models import Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import DailyBudget, UsageRecord


class UsageSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UsageRecord.objects.filter(user=request.user)
        today = qs.filter(created_at__date=timezone.localdate()).aggregate(
            tokens=Sum("tokens_in") + Sum("tokens_out"), cost=Sum("cost")
        )
        total = qs.aggregate(tokens=Sum("tokens_in") + Sum("tokens_out"), cost=Sum("cost"))
        return Response(
            {
                "today": {"tokens": today["tokens"] or 0, "cost": str(today["cost"] or 0)},
                "total": {"tokens": total["tokens"] or 0, "cost": str(total["cost"] or 0)},
                "records": qs.count(),
            }
        )


class BudgetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        budget = DailyBudget.objects.filter(user=request.user, date=timezone.localdate()).first()
        return Response(
            {
                "date": timezone.localdate(),
                "tokens_used": budget.tokens_used if budget else 0,
                "cost": str(budget.cost) if budget else "0",
            }
        )
