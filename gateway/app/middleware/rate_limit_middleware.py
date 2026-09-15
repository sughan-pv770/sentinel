"""
Rate Limit Middleware — fast-path protection before the ML pipeline.

Checks per-identity sliding window on every gateway request.
If the burst ceiling (500 req/window, configurable) is exceeded, the
request is rejected immediately with HTTP 429 and a revoke trigger is
enqueued so the SSE broadcast fires asynchronously.
"""
from __future__ import annotations
import asyncio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.services.rate_limiter import check_identity_rate, RateLimitExceeded
from app.utils.logger import get_logger

logger = get_logger("sentinelx.rate_limit_middleware")

# Paths that bypass identity rate limiting (static assets, health, metrics)
_BYPASS_PREFIXES = ("/health", "/metrics", "/static", "/portal", "/api/events")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # Skip rate limiting for bypass paths
        path = request.url.path
        if any(path.startswith(p) for p in _BYPASS_PREFIXES):
            return await call_next(request)

        identity_id = request.headers.get("x-identity-id")
        if not identity_id:
            return await call_next(request)

        try:
            from app.state_store import get_store
            store = get_store()
            result = await check_identity_rate(identity_id, store)

            # Attach remaining-burst header for clients to observe
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(result.limit)
            response.headers["X-RateLimit-Remaining"] = str(result.burst_remaining)
            response.headers["X-RateLimit-Window"] = str(settings.rate_limit_window_seconds)
            return response

        except RateLimitExceeded as exc:
            if exc.burst:
                # Hard surge (500+): trigger async revoke + SSE broadcast
                asyncio.create_task(_async_revoke_on_surge(identity_id, exc.count, exc.limit))

                from app.observability import rate_limit_hits_total
                rate_limit_hits_total.labels(key_type="identity_surge").inc()

                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_burst_surge",
                        "detail": (
                            f"Request rate ({exc.count}/{settings.rate_limit_window_seconds}s) "
                            f"exceeded the burst ceiling of {exc.limit}. "
                            "Session is being terminated for security."
                        ),
                        "identity_id": identity_id,
                    },
                    headers={"X-RateLimit-Limit": str(exc.limit), "X-RateLimit-Remaining": "0"},
                )

            from app.observability import rate_limit_hits_total
            rate_limit_hits_total.labels(key_type="identity").inc()
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": f"Too many requests. Limit: {exc.limit}/{settings.rate_limit_window_seconds}s",
                },
                headers={"X-RateLimit-Limit": str(exc.limit), "X-RateLimit-Remaining": "0"},
            )

        except Exception as exc:
            logger.error(f"Rate limiter error: {exc}")
            # Never let rate limiter failures block requests
            return await call_next(request)


async def _async_revoke_on_surge(identity_id: str, count: int, limit: int):
    """
    Background task: revoke all sessions for a surge identity and broadcast SSE.
    Runs outside the request path so the 429 response is returned instantly.
    """
    try:
        from app.state_store import get_store
        from app.services.session_service import revoke_all_sessions_and_broadcast
        store = get_store()
        await revoke_all_sessions_and_broadcast(
            identity_id=identity_id,
            reason="rate_burst_surge",
            risk_score=100.0,
            triggered_by="rate_limit_middleware",
            store=store,
        )
        from app.observability import sessions_revoked_total
        sessions_revoked_total.labels(triggered_by="rate_limit_middleware").inc()
        logger.warning(f"Async surge revoke completed  identity={identity_id}  count={count}")
    except Exception as exc:
        logger.error(f"Async surge revoke failed  identity={identity_id}  error={exc}")
