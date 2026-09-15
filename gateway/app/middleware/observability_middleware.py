"""
Observability middleware — records per-request Prometheus metrics
and injects SentinelX headers for downstream tracing.
"""
from __future__ import annotations
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Only import after app startup to avoid circular import during module load
        try:
            from app.observability import request_latency_ms, requests_total, _endpoint_group
            tier = response.headers.get("x-sentinelx-tier", "unknown")
            group = _endpoint_group(request.url.path)
            request_latency_ms.observe(elapsed_ms)
            requests_total.labels(tier=tier, endpoint_group=group).inc()
        except Exception:
            pass  # Never let observability failures affect the request

        return response
