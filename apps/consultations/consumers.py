from __future__ import annotations

import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.consultations.models import Consultation
from apps.consultations.services.events import register_local_consumer, unregister_local_consumer


class ConsultationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.group_name = None
        user = self.scope.get("user")
        consultation_id = self.scope["url_route"]["kwargs"]["consultation_id"]
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        owned = await database_sync_to_async(
            Consultation.objects.filter(pk=consultation_id, user_id=user.pk).exists
        )()
        if not owned:
            await self.close(code=4403)
            return
        self.group_name = f"consultation_{consultation_id}"
        self.consumer_loop = asyncio.get_running_loop()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        register_local_consumer(self.group_name, self.consumer_loop)
        await self.accept()

    async def disconnect(self, code):
        if self.group_name:
            unregister_local_consumer(self.group_name, self.consumer_loop)
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def agent_event(self, event):
        await self.send_json(event["payload"])
