from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from apps.consultations.models import Consultation, ConsultationRun, Message
from apps.consultations.services.langchain_history import LangChainHistory

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def consultation(username):
    user = get_user_model().objects.create_user(username=username)
    return Consultation.objects.create(user=user)


def completed_turn(session, user_text, assistant_text, *, status="succeeded"):
    request = Message.objects.create(consultation=session, role="user", content=user_text)
    reply = Message.objects.create(consultation=session, role="assistant", content=assistant_text)
    ConsultationRun.objects.create(
        consultation=session,
        message=request,
        reply=reply,
        client_request_id=uuid.uuid4(),
        status=status,
    )
    return request, reply


def test_langchain_history_uses_real_messages_and_excludes_unpublished(monkeypatch):
    session = consultation("history-approved")
    completed_turn(session, "咳嗽三天", "请补充症状")
    Message.objects.create(consultation=session, role="assistant", content="ORPHAN_CANDIDATE")
    completed_turn(session, "失败请求", "FAILED_CANDIDATE", status="failed")
    completed_turn(session, "需安全提醒的请求", "已审核安全提醒", status="blocked")
    Message.objects.create(consultation=session, role="system", content="PRIVATE_SYSTEM")
    cutoff = Message.objects.create(consultation=session, role="user", content="本次新输入")
    captured = []

    class ObservedHistory(InMemoryChatMessageHistory):
        def add_messages(self, messages):
            captured.extend(messages)
            super().add_messages(messages)

    monkeypatch.setattr(
        "apps.consultations.services.langchain_history.InMemoryChatMessageHistory", ObservedHistory
    )
    records = LangChainHistory().load(session.pk, before_message_id=cutoff.pk)
    assert records == [
        {"role": "user", "content": "咳嗽三天"},
        {"role": "assistant", "content": "请补充症状"},
        {"role": "user", "content": "失败请求"},
        {"role": "user", "content": "需安全提醒的请求"},
        {"role": "assistant", "content": "已审核安全提醒"},
    ]
    assert isinstance(captured[0], HumanMessage)
    assert isinstance(captured[1], AIMessage)


def test_same_provider_instance_never_reuses_another_users_history():
    first = consultation("history-first")
    second = consultation("history-second")
    _, first_reply = completed_turn(first, "FIRST_QUERY", "FIRST_APPROVED")
    _, second_reply = completed_turn(second, "SECOND_QUERY", "SECOND_APPROVED")
    provider = LangChainHistory()
    first_records = provider.load(first.pk, before_message_id=second_reply.pk + 1)
    second_records = provider.load(second.pk, before_message_id=second_reply.pk + 1)
    assert first_records == [
        {"role": "user", "content": "FIRST_QUERY"},
        {"role": "assistant", "content": "FIRST_APPROVED"},
    ]
    assert second_records == [
        {"role": "user", "content": "SECOND_QUERY"},
        {"role": "assistant", "content": "SECOND_APPROVED"},
    ]
    assert provider.load(first.pk, before_message_id=first_reply.pk + 1) == first_records


def test_latest_history_limit_and_read_only_behavior():
    session = consultation("history-limit")
    completed_turn(session, "旧问题", "旧回复")
    _, latest = completed_turn(session, "新问题", "新回复")
    with override_settings(HISTORY_MESSAGE_LIMIT=2), CaptureQueriesContext(connection) as queries:
        records = LangChainHistory().load(session.pk, before_message_id=latest.pk + 1)
    assert records == [
        {"role": "user", "content": "新问题"},
        {"role": "assistant", "content": "新回复"},
    ]
    assert queries.captured_queries
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries)
    with override_settings(HISTORY_MESSAGE_LIMIT=0):
        assert LangChainHistory().load(session.pk, before_message_id=latest.pk + 1) == []


def test_wrong_session_run_link_cannot_approve_an_assistant():
    first = consultation("history-mismatch-first")
    second = consultation("history-mismatch-second")
    request = Message.objects.create(consultation=second, role="user", content="OTHER_QUERY")
    candidate = Message.objects.create(consultation=first, role="assistant", content="MISMATCHED")
    ConsultationRun.objects.create(
        consultation=second,
        message=request,
        reply=candidate,
        client_request_id=uuid.uuid4(),
        status="succeeded",
    )
    assert LangChainHistory().load(first.pk, before_message_id=candidate.pk + 1) == []
