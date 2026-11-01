from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.services import get_overview


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            get_overview(request.user, global_scope=request.query_params.get("scope") != "own")
        )
