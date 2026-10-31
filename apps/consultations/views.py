"""问诊会话 API：列表/详情/创建/发消息（编排在 services.coordinator 里）。"""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.consultations.models import Consultation, Message
from apps.consultations.serializers import (
    ConsultationDetailSerializer,
    ConsultationListSerializer,
    MessageSerializer,
)


class ConsultationListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConsultationListSerializer

    def get_queryset(self):
        return Consultation.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ConsultationDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConsultationDetailSerializer

    def get_queryset(self):
        return Consultation.objects.filter(user=self.request.user)


class MessageCreateView(APIView):
    """追加一条用户消息，并同步推进一次多智能体协作。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        consultation = Consultation.objects.filter(pk=pk, user=request.user).first()
        if consultation is None:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        payload = MessageSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        message = Message.objects.create(
            consultation=consultation, role=Message.Role.USER, **payload.validated_data
        )

        from apps.consultations.services.coordinator import run_consultation_turn

        reply = run_consultation_turn(consultation, message)
        return Response(
            {
                "message": MessageSerializer(message).data,
                "reply": MessageSerializer(reply).data,
            },
            status=status.HTTP_201_CREATED,
        )
