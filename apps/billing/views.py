from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.services.queries import get_budget_summary, get_usage_summary


class UsageSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            get_usage_summary(request.user, global_scope=request.query_params.get("scope") == "all")
        )


class BudgetView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_budget_summary(request.user))
