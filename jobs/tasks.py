"""Celery task that drives a Job through its lifecycle and streams progress."""

import time

import structlog
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from config.metrics import JOB_DURATION, JOBS_FINISHED

from . import services
from .handlers import HANDLERS
from .models import Job, JobStatus

log = structlog.get_logger(__name__)

PROGRESS_PUBLISH_MIN_INTERVAL = 0.1  # seconds; coalesce bursts of progress events


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_job(self, job_id: str) -> None:
    structlog.contextvars.bind_contextvars(job_id=job_id)

    # Claim the row atomically; a duplicate delivery (acks_late) becomes a no-op.
    with transaction.atomic():
        job = Job.objects.select_for_update(skip_locked=True).filter(id=job_id).first()
        if job is None:
            log.warning("job_missing_or_locked")
            return
        if job.status != JobStatus.QUEUED:
            log.info("job_already_processed", status=job.status)
            return
        job.status = JobStatus.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

    services.publish_sync(job)
    log.info("job_started", kind=job.kind)

    last_publish = 0.0

    def report(progress: int) -> None:
        nonlocal last_publish
        job.progress = min(max(progress, 0), 100)
        now = time.monotonic()
        if now - last_publish >= PROGRESS_PUBLISH_MIN_INTERVAL or job.progress == 100:
            last_publish = now
            Job.objects.filter(id=job.id).update(progress=job.progress)
            services.publish_sync(job)

    started = time.perf_counter()
    try:
        handler = HANDLERS[job.kind]
        job.result = handler(job.payload, report)
        job.status = JobStatus.SUCCEEDED
        job.progress = 100
    except Exception as exc:  # noqa: BLE001 - we persist whatever went wrong
        job.status = JobStatus.FAILED
        job.error = f"{type(exc).__name__}: {exc}"[:2000]
        log.exception("job_failed")
    finally:
        elapsed = time.perf_counter() - started
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "progress", "result", "error", "finished_at"])
        services.publish_sync(job)
        services.record_finished_sync(job.status, elapsed)
        JOBS_FINISHED.labels(job.kind, job.status).inc()
        JOB_DURATION.labels(job.kind).observe(elapsed)
        log.info("job_finished", status=job.status, duration_ms=round(elapsed * 1000, 2))
