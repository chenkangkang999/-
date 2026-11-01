import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.consultations.consumers import ConsultationConsumer
from apps.consultations.models import Consultation

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]


async def test_websocket_rejects_anonymous_and_other_user():
    owner = await database_sync_to_async(get_user_model().objects.create_user)(username="ws-owner")
    other = await database_sync_to_async(get_user_model().objects.create_user)(username="ws-other")
    consultation = await database_sync_to_async(Consultation.objects.create)(user=owner)
    for user, code in [(AnonymousUser(), 4401), (other, 4403)]:
        communicator = WebsocketCommunicator(ConsultationConsumer.as_asgi(), "/ws/test/")
        communicator.scope["user"] = user
        communicator.scope["url_route"] = {"kwargs": {"consultation_id": consultation.pk}}
        connected, close_code = await communicator.connect()
        assert not connected
        assert close_code == code
        await communicator.disconnect()
    communicator = WebsocketCommunicator(ConsultationConsumer.as_asgi(), "/ws/test/")
    communicator.scope["user"] = owner
    communicator.scope["url_route"] = {"kwargs": {"consultation_id": consultation.pk}}
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


async def test_local_worker_publishes_on_consumer_loop(monkeypatch):
    import asyncio
    import uuid

    from channels.layers import get_channel_layer

    from apps.consultations.services.events import publish

    owner = await database_sync_to_async(get_user_model().objects.create_user)(
        username="ws-event-owner"
    )
    consultation = await database_sync_to_async(Consultation.objects.create)(user=owner)
    communicator = WebsocketCommunicator(ConsultationConsumer.as_asgi(), "/ws/test/")
    communicator.scope["user"] = owner
    communicator.scope["url_route"] = {"kwargs": {"consultation_id": consultation.pk}}
    connected, _ = await communicator.connect()
    assert connected
    consumer_loop = asyncio.get_running_loop()
    layer = get_channel_layer()
    original_send = layer.group_send

    async def checked_send(*args, **kwargs):
        assert asyncio.get_running_loop() is consumer_loop
        await original_send(*args, **kwargs)

    monkeypatch.setattr(layer, "group_send", checked_send)
    await asyncio.to_thread(
        publish,
        consultation.pk,
        run_id=uuid.uuid4(),
        trace_id="event-test",
        event_type="agent.completed",
        agent="explainer",
        status="completed",
        payload={"latency_ms": 42},
    )
    event = await communicator.receive_json_from(timeout=1)
    assert event["type"] == "agent.completed"
    assert event["payload"] == {"latency_ms": 42}
    await communicator.disconnect()
