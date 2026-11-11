import fakeredis
import fakeredis.aioredis
import pytest

from jobs import services


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """One in-memory Redis shared by the sync (worker) and async (web) clients."""
    server = fakeredis.FakeServer()
    sync_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    async_client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(services, "get_redis", lambda: sync_client)
    monkeypatch.setattr(services, "get_async_redis", lambda: async_client)
    return sync_client


@pytest.fixture
def make_job(db):
    from jobs.models import Job

    def _make(kind="primes", payload=None, **kwargs):
        return Job.objects.create(kind=kind, payload=payload or {"limit": 100}, **kwargs)

    return _make
