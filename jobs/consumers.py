"""WebSocket consumers (Channels). Fully async; never touch the ORM without sync_to_async."""

import structlog
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from config.metrics import WS_CONNECTIONS

from . import services
from .models import Job

log = structlog.get_logger(__name__)


class _BaseConsumer(AsyncJsonWebsocketConsumer):
    groups_joined: list[str]

    async def connect(self) -> None:
        self.groups_joined = []
        await self.accept()
        WS_CONNECTIONS.inc()

    async def disconnect(self, code: int) -> None:
        for group in self.groups_joined:
            await self.channel_layer.group_discard(group, self.channel_name)
        WS_CONNECTIONS.dec()

    async def join(self, group: str) -> None:
        await self.channel_layer.group_add(group, self.channel_name)
        self.groups_joined.append(group)

    async def job_event(self, event: dict) -> None:
        """Handler for `{"type": "job.event"}` messages from the channel layer."""
        await self.send_json({"type": "job", "job": event["job"]})

    async def receive_json(self, content: dict, **kwargs) -> None:
        if content.get("action") == "ping":
            await self.send_json({"type": "pong"})
        else:
            await self.send_json({"type": "error", "detail": "unknown action"})


class JobConsumer(_BaseConsumer):
    """ws://host/ws/jobs/<id>/ - progress for a single job; replays current state on connect."""

    async def connect(self) -> None:
        job_id = self.scope["url_route"]["kwargs"]["job_id"]
        job = await database_sync_to_async(lambda: Job.objects.filter(id=job_id).first())()
        if job is None:
            await self.close(code=4004)
            return
        await super().connect()
        # Subscribe first, then send the snapshot: no gap where an update could be lost.
        await self.join(services.job_group(job_id))
        await self.send_json({"type": "job", "job": job.to_event()})
        log.info("ws_connected", job_id=str(job_id))


class JobFeedConsumer(_BaseConsumer):
    """ws://host/ws/jobs/ - firehose of every job event."""

    async def connect(self) -> None:
        await super().connect()
        await self.join(services.FEED_GROUP)
        log.info("ws_feed_connected")
