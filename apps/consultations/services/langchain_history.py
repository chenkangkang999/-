"""LangChain message history over this consultation's approved persisted messages.

Django remains the persistent store. Each load builds a fresh LangChain history;
there is no process-global session cache and this adapter never writes messages.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from apps.consultations.models import ConsultationRun, Message


class LangChainHistory:
    """Implement HistoryPort without exposing unreviewed or other-session replies."""

    def load(self, consultation_id: int, *, before_message_id: int) -> list[dict[str, str]]:
        limit = max(0, int(settings.HISTORY_MESSAGE_LIMIT))
        if limit == 0:
            return []
        # Published assistants must be the reply of a completed, same-session run.
        # Orphan/manual assistant messages and replies from failed runs are excluded.
        approved = Q(role=Message.Role.USER) | Q(
            role=Message.Role.ASSISTANT,
            response_run__consultation_id=consultation_id,
            response_run__status__in=[
                ConsultationRun.Status.SUCCEEDED,
                ConsultationRun.Status.BLOCKED,
            ],
        )
        messages = list(
            Message.objects.filter(
                consultation_id=consultation_id,
                id__lt=before_message_id,
            ).filter(approved).order_by("-id")[:limit]
        )
        history = InMemoryChatMessageHistory()
        history.add_messages([
            HumanMessage(content=message.content)
            if message.role == Message.Role.USER
            else AIMessage(content=message.content)
            for message in reversed(messages)
        ])
        return [
            {
                "role": "user" if isinstance(message, HumanMessage) else "assistant",
                "content": message.content,
            }
            for message in history.messages
        ]
