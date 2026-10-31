from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ConsultationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.group_name = f"consultation_{self.scope['url_route']['kwargs']['consultation_id']}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def agent_event(self, event):
        await self.send_json(event["payload"])
