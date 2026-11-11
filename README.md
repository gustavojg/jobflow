# jobflow

A small but production-shaped **real-time job pipeline** in Python. Clients submit jobs over a REST API, a Celery worker pool executes them, and progress is streamed live to browsers over WebSockets.

```
 client ──POST /api/jobs/──▶ Django (ASGI / uvicorn) ──enqueue──▶ Redis (broker)
   ▲                              │                                    │
   │  ws://…/ws/jobs/<id>/        │ Postgres (jobs: source of truth)   ▼
   └──────◀── Channels ◀── Redis channel layer ◀── group_send ── Celery worker
                                                                        │
                                              Redis (live stats) ◀──────┘
```

It exists to demonstrate, end to end and with tests, this stack:

| Area | What's here |
|---|---|
| **Async Python / ASGI** | Native `async` Django views, async middleware, `AsyncJsonWebsocketConsumer` via Django Channels, served by uvicorn |
| **API development** | Django REST Framework viewset with validation, filtering, keyset (cursor) pagination, throttling |
| **Real-time** | Per-job and firehose WebSocket feeds; snapshot-then-stream to avoid lost updates; origin validation |
| **Message queue** | Celery on Redis: `acks_late`, prefetch 1, time limits, autoretry with backoff, idempotent task via `SELECT … FOR UPDATE SKIP LOCKED` |
| **SQL + NoSQL** | PostgreSQL as the system of record; Redis for hot counters (per-minute throughput buckets with TTL) and pub/sub fan-out |
| **Logging** | `structlog` JSON logs; `X-Request-ID` propagated through contextvars into every log line, including Celery tasks |
| **Monitoring** | Prometheus `/metrics` (request latency histograms, job durations, open sockets); `/healthz` liveness and `/readyz` readiness with concurrent, deadline-bound dependency checks |
| **Performance** | Progress events coalesced to ≤10/s per job; `on_commit` enqueueing (no worker ever sees an uncommitted row); persistent DB connections; cursor pagination is O(1) per page |
| **Testing** | 30 pytest tests, ~2s, zero external services: SQLite, in-memory channel layer, eager Celery, `fakeredis`. Covers API, task lifecycle, failure path, idempotency, websockets, health endpoints |
| **Production** | Multi-stage Docker image (non-root, healthcheck), Compose stack, GitHub Actions CI (ruff + pytest + image build), 12-factor config via env vars |

## Run it

```bash
docker compose up --build
```

Port 8000 taken? `WEB_PORT=8080 docker compose up --build` and pass `--base http://localhost:8080` to the demo.

Then, in another terminal:

```bash
uv run python scripts/demo.py --count 20 --kind primes
```

The demo submits 20 jobs concurrently, reports submit latency, and prints each job's progress as it streams in over the WebSocket feed.

Manual poking:

```bash
curl -s -X POST localhost:8000/api/jobs/ -H 'Content-Type: application/json' \
     -d '{"kind":"primes","payload":{"limit":5000000}}'
```

```bash
curl -s localhost:8000/api/stats
```

```bash
curl -s localhost:8000/readyz
```

```bash
curl -s localhost:8000/metrics | grep jobflow_
```

Job kinds: `primes` (CPU-bound segmented sieve), `checksum` (iterated SHA-256), `sleep` (IO-bound stand-in). Add your own in `jobs/handlers.py`: a function `(payload, report) -> result`.

## Develop

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```

Run against real services without Docker for the app itself:

```bash
docker compose up -d db redis
```

```bash
DATABASE_URL=postgres://jobflow:jobflow@localhost:5432/jobflow uv run python manage.py migrate
```

```bash
DATABASE_URL=postgres://jobflow:jobflow@localhost:5432/jobflow uv run uvicorn config.asgi:application --reload
```

```bash
DATABASE_URL=postgres://jobflow:jobflow@localhost:5432/jobflow uv run celery -A config worker -l INFO
```

## Layout

```
config/          settings, ASGI entrypoint, Celery app, logging, middleware, metrics
jobs/
  models.py      Job lifecycle (queued → running → succeeded|failed)
  handlers.py    the actual work, one function per job kind
  tasks.py       Celery task: claim row, run handler, stream progress, persist
  services.py    Redis stats + channel-layer fan-out (the only side-effect boundary)
  consumers.py   WebSocket consumers
  views.py       DRF viewset + async ops endpoints
  tests/         pytest suite (no external services needed)
scripts/demo.py  concurrent submit + live progress client
```

## Design notes

- **Postgres is the truth, Redis is a cache.** Counters in Redis can be lost without losing jobs; `/api/stats` is cheap because it never touches Postgres.
- **Exactly-once-ish processing.** `acks_late` means a crashed worker's task is redelivered; the task claims the row with `SKIP LOCKED` and exits early if it is no longer `queued`, so redelivery is a no-op.
- **No lost WebSocket updates.** The consumer subscribes to the job's group *before* sending the current snapshot. A client therefore sees either the update in the snapshot or as a message, never neither.
- **Backpressure on progress.** Handlers may call `report()` thousands of times; the task publishes at most every 100 ms (and always at 100 %), keeping Redis and sockets quiet under load.
- **Readiness is concurrent and bounded.** `/readyz` pings Postgres and Redis in parallel with a 2 s deadline each, so a slow dependency cannot make the probe itself slow.

## License

MIT
