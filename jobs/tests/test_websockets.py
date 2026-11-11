import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from config.asgi import application
from jobs import services
from jobs.models import JobStatus

pytestmark = pytest.mark.django_db(transaction=True)


OK_HEADERS = [(b"host", b"localhost"), (b"origin", b"http://localhost")]


async def _connect(path: str) -> WebsocketCommunicator:
    comm = WebsocketCommunicator(application, path, headers=OK_HEADERS)
    connected, _ = await comm.connect()
    assert connected
    return comm


async def test_job_socket_replays_snapshot_then_streams_updates(make_job):
    job = await sync_to_async(make_job)()
    comm = await _connect(f"/ws/jobs/{job.id}/")
    try:
        snapshot = await comm.receive_json_from()
        assert snapshot["type"] == "job"
        assert snapshot["job"]["status"] == "queued"

        job.status = JobStatus.RUNNING
        job.progress = 42
        await sync_to_async(services.publish_sync)(job)

        update = await comm.receive_json_from()
        assert update["job"]["progress"] == 42
        assert update["job"]["status"] == "running"
    finally:
        await comm.disconnect()


async def test_job_socket_closes_for_unknown_job():
    comm = WebsocketCommunicator(
        application,
        "/ws/jobs/00000000-0000-0000-0000-000000000000/",
        headers=OK_HEADERS,
    )
    connected, code = await comm.connect()
    assert not connected
    assert code == 4004


async def test_feed_socket_receives_every_job(make_job):
    comm = await _connect("/ws/jobs/")
    try:
        a = await sync_to_async(make_job)()
        b = await sync_to_async(make_job)()
        await sync_to_async(services.publish_sync)(a)
        await sync_to_async(services.publish_sync)(b)

        ids = {(await comm.receive_json_from())["job"]["id"] for _ in range(2)}
        assert ids == {str(a.id), str(b.id)}
    finally:
        await comm.disconnect()


async def test_ping_pong_and_unknown_action():
    comm = await _connect("/ws/jobs/")
    try:
        await comm.send_json_to({"action": "ping"})
        assert await comm.receive_json_from() == {"type": "pong"}
        await comm.send_json_to({"action": "dance"})
        assert (await comm.receive_json_from())["type"] == "error"
    finally:
        await comm.disconnect()


async def test_rejects_disallowed_or_missing_origin():
    comm = WebsocketCommunicator(application, "/ws/jobs/", headers=[(b"host", b"localhost")])
    connected, _ = await comm.connect()
    assert not connected

    comm = WebsocketCommunicator(
        application,
        "/ws/jobs/",
        headers=[(b"host", b"localhost"), (b"origin", b"https://evil.example")],
    )
    connected, _ = await comm.connect()
    assert not connected
