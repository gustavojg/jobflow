"""HTTP surface.

- DRF viewset for the Job resource (sync ORM, runs in a worker thread under ASGI).
- Native async views for the hot, read-only paths (stats, readiness, metrics) so they
  never block the event loop on Redis round-trips.
"""

import asyncio

import structlog
from asgiref.sync import sync_to_async
from django.db import connection, transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from rest_framework import mixins, viewsets

from config.metrics import JOBS_CREATED

from . import services
from .models import Job
from .serializers import JobSerializer
from .tasks import run_job

log = structlog.get_logger(__name__)


class JobViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Job.objects.all()
    serializer_class = JobSerializer
    filterset_fields = ["status", "kind"]

    def get_queryset(self):
        qs = super().get_queryset()
        for field in self.filterset_fields:
            if value := self.request.query_params.get(field):
                qs = qs.filter(**{field: value})
        return qs

    def perform_create(self, serializer):
        job = serializer.save()
        JOBS_CREATED.labels(job.kind).inc()
        services.record_created_sync()
        # Enqueue only once the row is committed, so the worker can always find it.
        transaction.on_commit(lambda: run_job.delay(str(job.id)))
        log.info("job_enqueued", job_id=str(job.id), kind=job.kind)


@require_GET
async def stats(request):
    return JsonResponse(await services.read_stats())


@require_GET
async def healthz(request):
    """Liveness: the process is up and serving."""
    return JsonResponse({"status": "ok"})


@require_GET
async def readyz(request):
    """Readiness: dependencies reachable. Checked concurrently with a hard deadline."""

    def db_ping() -> None:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")

    async def redis_ping() -> None:
        await services.get_async_redis().ping()

    checks = {"database": sync_to_async(db_ping)(), "redis": redis_ping()}
    results = await asyncio.gather(
        *(asyncio.wait_for(c, timeout=2.0) for c in checks.values()), return_exceptions=True
    )
    report = {
        name: ("ok" if not isinstance(r, BaseException) else f"error: {r!r}")
        for name, r in zip(checks, results, strict=True)
    }
    healthy = all(v == "ok" for v in report.values())
    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": report},
        status=200 if healthy else 503,
    )


@require_GET
async def metrics(request):
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
