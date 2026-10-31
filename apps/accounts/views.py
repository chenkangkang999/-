from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import PatientProfile


class MeView(APIView):
    """当前登录用户 + 患者档案（没有就返回空档案，不自动建）。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = PatientProfile.objects.filter(user=request.user).first()
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
                "profile": None
                if profile is None
                else {
                    "display_name": profile.display_name,
                    "birth_date": profile.birth_date,
                    "sex": profile.sex,
                    "allergies": profile.allergies,
                    "chronic_conditions": profile.chronic_conditions,
                },
            }
        )
