"""Deliver local events on the consumer loop; Redis supports independent worker loops."""

from __future__ import annotations

import asyncio
import logging
import threading

from asgiref.sync import async_to_sync
from channels.layers import InMemoryChannelLayer, get_channel_layer
from django.utils import timezone

logger = logging.getLogger(__name__)
_loop_lock = threading.Lock()
_local_loops: dict[str, dict[asyncio.AbstractEventLoop, int]] = {}


def register_local_consumer(group, loop):
    with _loop_lock:
        counts = _local_loops.setdefault(group, {})
        counts[loop] = counts.get(loop, 0) + 1


def unregister_local_consumer(group, loop):
    with _loop_lock:
        counts = _local_loops.get(group, {})
        if loop in counts:
            counts[loop] -= 1
            if counts[loop] <= 0:
                del counts[loop]
        if not counts:
            _local_loops.pop(group, None)


def _delivery_done(future):
    try:
        future.result()
    except Exception:
        logger.warning("WebSocket delivery failed; persisted REST state is available")


def publish(
    consultation_id, *, run_id, trace_id, event_type, agent=None, status=None, payload=None
):
    event = {
        "type": event_type,
        "run_id": str(run_id),
        "trace_id": str(trace_id),
        "timestamp": timezone.now().isoformat(),
        "payload": payload or {},
    }
    if agent is not None:
        event["agent"] = agent
    if status is not None:
        event["status"] = status
    group = f"consultation_{consultation_id}"
    message = {"type": "agent.event", "payload": event}
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        if isinstance(layer, InMemoryChannelLayer):
            with _loop_lock:
                loops = [loop for loop in _local_loops.get(group, {}) if loop.is_running()]
            # In-memory queues must be touched on the consumer event loop.
            # No active browser means there is no notification to deliver.
            for loop in loops[:1]:
                asyncio.run_coroutine_threadsafe(
                    layer.group_send(group, message), loop
                ).add_done_callback(_delivery_done)
        else:
            async_to_sync(layer.group_send)(group, message)
    except Exception:
        logger.warning("WebSocket notification unavailable run=%s", run_id)
