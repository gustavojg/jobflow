"""Side-effect boundary: Redis (live stats) and the channel layer (websocket fan-out).

Redis holds hot, ephemeral counters that would be wasteful to compute from
Postgres on every dashboard poll. Postgres stays the source of truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cache

import redis
import redis.asyncio as aioredis
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

FEED_GROUP = "jobs.feed"
STATS_KEY = "jobflow:stats"
THROUGHPUT_PREFIX = "jobflow:throughput:"  # per-minute buckets, short TTL
WINDOW_MINUTES = 5


def job_group(job_id) -> str:
    return f"job.{job_id}"


@cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@cache
def get_async_redis() -> aioredis.Redis:
    return aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


# --- websocket fan-out ----------------------------------------------------------


def publish_sync(job) -> None:
    """Push a job event to its own group and the global feed (called from Celery)."""
    layer = get_channel_layer()
    message = {"type": "job.event", "job": job.to_event()}
    send = async_to_sync(layer.group_send)
    send(job_group(job.id), message)
    send(FEED_GROUP, message)


# --- live stats (Redis) --------------------------------------------------------


def _minute_bucket(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return THROUGHPUT_PREFIX + now.strftime("%Y%m%d%H%M")


def record_finished_sync(status: str, duration: float) -> None:
    r = get_redis()
    with r.pipeline(transaction=False) as pipe:
        pipe.hincrby(STATS_KEY, status, 1)
        pipe.hincrbyfloat(STATS_KEY, "duration_total", duration)
        bucket = _minute_bucket()
        pipe.incr(bucket)
        pipe.expire(bucket, (WINDOW_MINUTES + 1) * 60)
        pipe.execute()


def record_created_sync() -> None:
    get_redis().hincrby(STATS_KEY, "created", 1)


async def read_stats() -> dict:
    r = get_async_redis()
    now = datetime.now(UTC)
    buckets = [
        _minute_bucket(now.replace(second=0, microsecond=0) - _minutes(i))
        for i in range(WINDOW_MINUTES)
    ]
    async with r.pipeline(transaction=False) as pipe:
        pipe.hgetall(STATS_KEY)
        pipe.mget(buckets)
        raw, per_minute = await pipe.execute()

    created = int(raw.get("created", 0))
    succeeded = int(raw.get("succeeded", 0))
    failed = int(raw.get("failed", 0))
    finished = succeeded + failed
    total_duration = float(raw.get("duration_total", 0.0))
    recent = sum(int(x or 0) for x in per_minute)
    return {
        "created": created,
        "succeeded": succeeded,
        "failed": failed,
        "in_flight": max(created - finished, 0),
        "avg_duration_seconds": round(total_duration / finished, 3) if finished else None,
        "finished_last_5m": recent,
        "throughput_per_minute": round(recent / WINDOW_MINUTES, 2),
    }


def _minutes(n: int):
    from datetime import timedelta

    return timedelta(minutes=n)
