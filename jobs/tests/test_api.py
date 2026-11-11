import pytest
from rest_framework.test import APIClient

from jobs.models import Job, JobStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def test_create_job_enqueues_after_commit(client, django_capture_on_commit_callbacks, fake_redis):
    with django_capture_on_commit_callbacks(execute=True):
        res = client.post("/api/jobs/", {"kind": "primes", "payload": {"limit": 50}}, format="json")

    assert res.status_code == 201, res.content
    job = Job.objects.get(id=res.data["id"])
    assert job.status == JobStatus.SUCCEEDED  # eager Celery ran it on commit
    assert job.result["count"] == 15
    assert fake_redis.hget("jobflow:stats", "created") == "1"
    assert res["X-Request-ID"]


def test_create_job_rejects_unknown_kind(client):
    res = client.post("/api/jobs/", {"kind": "nope", "payload": {}}, format="json")
    assert res.status_code == 400
    assert "kind" in res.data


def test_create_job_rejects_non_object_payload(client):
    res = client.post("/api/jobs/", {"kind": "sleep", "payload": [1, 2]}, format="json")
    assert res.status_code == 400
    assert "payload" in res.data


def test_list_filters_by_status(client, make_job):
    make_job(status=JobStatus.SUCCEEDED)
    make_job(status=JobStatus.QUEUED)

    res = client.get("/api/jobs/?status=queued")
    assert res.status_code == 200
    assert [j["status"] for j in res.data["results"]] == ["queued"]


def test_retrieve_missing_job_is_404(client):
    assert client.get("/api/jobs/00000000-0000-0000-0000-000000000000/").status_code == 404


def test_request_id_header_is_echoed(client):
    res = client.get("/api/jobs/", HTTP_X_REQUEST_ID="abc123")
    assert res["X-Request-ID"] == "abc123"
