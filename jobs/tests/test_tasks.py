import pytest

from jobs.models import JobStatus
from jobs.tasks import run_job

pytestmark = pytest.mark.django_db


def test_run_job_succeeds_and_persists_result(make_job, fake_redis):
    job = make_job(kind="primes", payload={"limit": 100})
    run_job(str(job.id))
    job.refresh_from_db()

    assert job.status == JobStatus.SUCCEEDED
    assert job.progress == 100
    assert job.result == {"count": 25, "limit": 100}
    assert job.started_at and job.finished_at and job.duration_seconds >= 0
    assert fake_redis.hget("jobflow:stats", "succeeded") == "1"


def test_run_job_records_failure_without_raising(make_job, fake_redis):
    job = make_job(kind="primes", payload={"limit": "not-a-number"})
    run_job(str(job.id))
    job.refresh_from_db()

    assert job.status == JobStatus.FAILED
    assert job.error.startswith("ValueError")
    assert job.result is None
    assert fake_redis.hget("jobflow:stats", "failed") == "1"


def test_run_job_is_idempotent_on_redelivery(make_job):
    job = make_job(kind="checksum", payload={"text": "x", "rounds": 10})
    run_job(str(job.id))
    job.refresh_from_db()
    first_finished = job.finished_at

    run_job(str(job.id))  # acks_late duplicate delivery
    job.refresh_from_db()
    assert job.finished_at == first_finished


def test_run_job_ignores_unknown_id(db):
    run_job("00000000-0000-0000-0000-000000000000")  # must not raise
