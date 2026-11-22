"""Pure ASGI request observability middleware that preserves streaming."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL

logger = logging.getLogger(__name__)


class RequestObservabilityMiddleware:
    """Attach a request ID, security headers, latency metrics, and access logs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        scope["request_id"] = request_id
        started = time.perf_counter()
        status_code = 500

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Process-Time"] = f"{time.perf_counter() - started:.6f}"
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            duration = time.perf_counter() - started
            method = str(scope.get("method", "UNKNOWN"))
            route = scope.get("route")
            path = str(getattr(route, "path", "unmatched"))
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path=path,
                status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration)
            logger.info(
                "http_request method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
                method,
                path,
                status_code,
                duration * 1000,
                request_id,
            )


def _request_id(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key == b"x-request-id":
            candidate = value.decode("latin-1").strip()
            if (
                candidate
                and len(candidate) <= 64
                and all(character.isalnum() or character in "-_" for character in candidate)
            ):
                return candidate
    return uuid4().hex
