"""Async-capable middleware: request-id propagation and Prometheus metrics."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from asgiref.sync import iscoroutinefunction
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import sync_and_async_middleware

from .metrics import HTTP_LATENCY, HTTP_REQUESTS

log = structlog.get_logger(__name__)

Handler = Callable[[HttpRequest], HttpResponse | Awaitable[HttpResponse]]


def _route(request: HttpRequest) -> str:
    match = getattr(request, "resolver_match", None)
    return (match.route if match and match.route else request.path) or "unknown"


@sync_and_async_middleware
def RequestContextMiddleware(get_response: Handler):  # noqa: N802 (Django naming)
    def bind(request: HttpRequest) -> str:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.path)
        return request_id

    if iscoroutinefunction(get_response):

        async def middleware(request: HttpRequest) -> HttpResponse:
            request_id = bind(request)
            response = await get_response(request)
            response["X-Request-ID"] = request_id
            return response

    else:

        def middleware(request: HttpRequest) -> HttpResponse:
            request_id = bind(request)
            response = get_response(request)
            response["X-Request-ID"] = request_id
            return response

    return middleware


@sync_and_async_middleware
def MetricsMiddleware(get_response: Handler):  # noqa: N802
    def record(request: HttpRequest, response: HttpResponse, started: float) -> None:
        elapsed = time.perf_counter() - started
        route = _route(request)
        HTTP_REQUESTS.labels(request.method, route, response.status_code).inc()
        HTTP_LATENCY.labels(request.method, route).observe(elapsed)
        log.info(
            "http_request",
            method=request.method,
            route=route,
            status=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
        )

    if iscoroutinefunction(get_response):

        async def middleware(request: HttpRequest) -> HttpResponse:
            started = time.perf_counter()
            response = await get_response(request)
            record(request, response, started)
            return response

    else:

        def middleware(request: HttpRequest) -> HttpResponse:
            started = time.perf_counter()
            response = get_response(request)
            record(request, response, started)
            return response

    return middleware
