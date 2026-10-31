"""WebSocket 路由：按会话 id 分组，用于流式推送 Agent 状态。"""
from __future__ import annotations

from django.urls import path

from apps.consultations.consumers import ConsultationConsumer

websocket_urlpatterns = [
    path("ws/consultations/<int:consultation_id>/", ConsultationConsumer.as_asgi()),
]
