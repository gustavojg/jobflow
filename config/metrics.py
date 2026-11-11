"""Prometheus metrics shared by web, websocket and worker processes."""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "jobflow_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "jobflow_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
WS_CONNECTIONS = Gauge("jobflow_ws_connections", "Open websocket connections")
JOBS_CREATED = Counter("jobflow_jobs_created_total", "Jobs submitted", ["kind"])
JOBS_FINISHED = Counter("jobflow_jobs_finished_total", "Jobs finished", ["kind", "status"])
JOB_DURATION = Histogram(
    "jobflow_job_duration_seconds",
    "Job processing time",
    ["kind"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
