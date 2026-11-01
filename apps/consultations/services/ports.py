"""Platform-side ports. Algorithm and history providers can be replaced independently."""

from __future__ import annotations

from typing import Any, Protocol

from agents.base.context import AgentContext


class CoordinatorPort(Protocol):
    def run(self, text: str, context: AgentContext, enable_debate: bool = True) -> Any: ...


class HistoryPort(Protocol):
    def load(self, consultation_id: int, *, before_message_id: int) -> list[dict[str, str]]: ...


class DatabaseHistory:
    """Read persisted, approved messages; a LangChain adapter may replace this port."""

    def load(self, consultation_id: int, *, before_message_id: int) -> list[dict[str, str]]:
        from django.conf import settings

        from apps.consultations.models import Message

        messages = list(
            Message.objects.filter(
                consultation_id=consultation_id,
                id__lt=before_message_id,
                role__in=[Message.Role.USER, Message.Role.ASSISTANT],
            ).order_by("-id")[: settings.HISTORY_MESSAGE_LIMIT]
        )
        return [{"role": item.role, "content": item.content} for item in reversed(messages)]
