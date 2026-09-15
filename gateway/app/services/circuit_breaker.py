"""
Circuit Breaker for the ML inference engine.

States:
  CLOSED    — Normal operation. Failures are counted.
  OPEN      — ML is unavailable; all calls fast-fail with fallback score.
  HALF_OPEN — Recovery probe: one test call allowed. If it succeeds,
               circuit resets to CLOSED; if it fails, stays OPEN.

This protects the request pipeline from ML model degradation while
respecting the 50ms SLA budget (ADR-004).
"""
from __future__ import annotations
import asyncio
import time
from enum import Enum
from typing import Callable, Any, Optional
from app.utils.logger import get_logger

logger = get_logger("sentinelx.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpen(Exception):
    """Raised when a call is attempted while the circuit is OPEN."""
    pass


class CircuitBreaker:
    """
    Async-safe in-process circuit breaker.

    Usage:
        cb = CircuitBreaker(failure_threshold=5, recovery_window_s=30)
        try:
            result = await cb.call(some_async_fn, arg1, arg2)
        except CircuitBreakerOpen:
            result = fallback_value
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_window_s: int = 30,
        success_threshold: int = 2,    # successes needed in HALF_OPEN to fully CLOSE
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_window_s = recovery_window_s
        self.success_threshold = success_threshold
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_ts: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def _should_attempt_reset(self) -> bool:
        """Return True if enough time has elapsed to probe recovery."""
        if self._last_failure_ts is None:
            return False
        return (time.monotonic() - self._last_failure_ts) >= self.recovery_window_s

    async def call(self, fn: Callable, *args, timeout_s: Optional[float] = None, **kwargs) -> Any:
        """
        Execute `fn(*args, **kwargs)` under circuit breaker protection.

        Args:
            fn:        Async callable to protect.
            timeout_s: Optional per-call timeout (seconds). None = no timeout.

        Raises:
            CircuitBreakerOpen: When circuit is OPEN and recovery window has not elapsed.
            asyncio.TimeoutError: When call exceeds timeout_s.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info(f"[circuit_breaker:{self.name}] → HALF_OPEN (probing recovery)")
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit '{self.name}' is OPEN. "
                        f"Next probe in {self.recovery_window_s - (time.monotonic() - (self._last_failure_ts or 0)):.1f}s"
                    )

        # Execute the call (outside the lock to allow concurrent calls in CLOSED/HALF_OPEN)
        try:
            if timeout_s is not None:
                result = await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout_s)
            else:
                result = await fn(*args, **kwargs)

            await self._on_success()
            return result

        except CircuitBreakerOpen:
            raise
        except Exception as exc:
            await self._on_failure(exc)
            raise

    async def _on_success(self):
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._last_failure_ts = None
                    logger.info(f"[circuit_breaker:{self.name}] → CLOSED (recovered)")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset on success

    async def _on_failure(self, exc: Exception):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_ts = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — stay OPEN
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[circuit_breaker:{self.name}] HALF_OPEN probe failed → OPEN again. "
                    f"Error: {exc}"
                )
            elif self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    f"[circuit_breaker:{self.name}] CLOSED → OPEN after {self._failure_count} failures. "
                    f"Recovery in {self.recovery_window_s}s. Last error: {exc}"
                )

    def reset(self):
        """Manually reset circuit to CLOSED (admin override)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_ts = None
        logger.info(f"[circuit_breaker:{self.name}] manually reset → CLOSED")

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_window_s": self.recovery_window_s,
            "last_failure_ts": self._last_failure_ts,
        }


# ── Singleton ML circuit breaker ───────────────────────────────────────────────

_ml_breaker: Optional[CircuitBreaker] = None


def get_ml_circuit_breaker() -> CircuitBreaker:
    global _ml_breaker
    if _ml_breaker is None:
        from app.config import settings
        _ml_breaker = CircuitBreaker(
            failure_threshold=settings.ml_circuit_breaker_threshold,
            recovery_window_s=settings.ml_circuit_breaker_recovery_s,
            name="ml_engine",
        )
    return _ml_breaker
