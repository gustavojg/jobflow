import pytest
from django.test import AsyncClient

from jobs import services
from jobs.models import JobStatus
from jobs.tasks import run_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def aclient():
    return AsyncClient()


async def test_healthz(aclient):
    res = await aclient.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_readyz_reports_dependencies(aclient):
    res = await aclient.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def test_readyz_degrades_when_redis_is_down(aclient, monkeypatch):
    class Broken:
        async def ping(self):
            raise ConnectionError("boom")

    monkeypatch.setattr(services, "get_async_redis", lambda: Broken())
    res = await aclient.get("/readyz")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"].startswith("error")


async def test_metrics_exposes_prometheus_text(aclient):
    res = await aclient.get("/metrics")
    assert res.status_code == 200
    assert b"jobflow_http_requests_total" in res.content


async def test_stats_aggregates_from_redis(aclient, make_job):
    from asgiref.sync import sync_to_async

    job = await sync_to_async(make_job)(kind="checksum", payload={"text": "a", "rounds": 5})
    await sync_to_async(run_job)(str(job.id))
    services.record_created_sync()

    res = await aclient.get("/api/stats")
    body = res.json()
    assert res.status_code == 200
    assert body["succeeded"] == 1 and body["failed"] == 0
    assert body["created"] == 1 and body["in_flight"] == 0
    assert body["finished_last_5m"] == 1
    assert body["avg_duration_seconds"] is not None

    job.status = JobStatus.SUCCEEDED


async def test_home_serves_the_ui(aclient):
    res = await aclient.get("/")
    assert res.status_code == 200
    assert b"<title>jobflow</title>" in res.content
    assert b"/ws/jobs/" in res.content
