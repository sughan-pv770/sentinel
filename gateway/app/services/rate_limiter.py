"""
Rate Limiter — sliding window implementation backed by the store.

Two modes:
  1. Per-identity sliding window  — limits requests from one identity
  2. Per-IP sliding window        — protects against credential stuffing on /login

The middleware calls check() which returns immediately (< 1ms with Redis
pipeline). If the limit is exceeded it raises RateLimitExceeded so the
middleware can return 429 before any further processing.
"""
from __future__ import annotations
from dataclasses import dataclass
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger("sentinelx.rate_limiter")


class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded."""
    def __init__(self, key: str, count: int, limit: int, burst: bool = False):
        self.key = key
        self.count = count
        self.limit = limit
        self.burst = burst  # True when this is the hard surge ceiling (500+)
        super().__init__(f"Rate limit exceeded for {key}: {count}/{limit}")


@dataclass
class RateLimitResult:
    key: str
    count: int
    limit: int
    burst_remaining: int
    exceeded: bool
    is_surge: bool = False  # True if count >= burst_ceiling (triggers REVOKE tier)


async def check_identity_rate(
    identity_id: str,
    store,
    window_seconds: int = None,
    step_up_threshold: int = None,
    burst_ceiling: int = None,
) -> RateLimitResult:
    """
    Check per-identity sliding window rate.

    Returns RateLimitResult.
    Raises RateLimitExceeded if the hard burst ceiling is hit
    (caller should trigger REVOKE, not just 429).
    """
    window_seconds = window_seconds or settings.rate_limit_window_seconds
    step_up_threshold = step_up_threshold or settings.rate_limit_step_up_threshold
    burst_ceiling = burst_ceiling or settings.rate_limit_burst_ceiling

    key = f"identity:{identity_id}"
    state = await store.rate_limit_check(key, window_seconds, burst_ceiling)
    count = state["count"]
    is_surge = count >= burst_ceiling

    if is_surge:
        logger.warning(
            f"RATE BURST SURGE  identity={identity_id}  "
            f"count={count}  ceiling={burst_ceiling}  window={window_seconds}s"
        )
        raise RateLimitExceeded(key=key, count=count, limit=burst_ceiling, burst=True)

    return RateLimitResult(
        key=key,
        count=count,
        limit=burst_ceiling,
        burst_remaining=state["burst_remaining"],
        exceeded=state["exceeded"],
        is_surge=False,
    )


async def check_ip_rate(
    ip: str,
    store,
    window_seconds: int = 60,
    limit: int = 20,  # 20 login attempts per minute per IP
) -> RateLimitResult:
    """Per-IP rate limiter (credential stuffing / brute-force protection)."""
    key = f"ip:{ip}"
    state = await store.rate_limit_check(key, window_seconds, limit)

    if state["exceeded"]:
        raise RateLimitExceeded(key=key, count=state["count"], limit=limit, burst=False)

    return RateLimitResult(
        key=key,
        count=state["count"],
        limit=limit,
        burst_remaining=state["burst_remaining"],
        exceeded=False,
    )
