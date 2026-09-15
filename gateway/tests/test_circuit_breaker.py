"""
Tests for the circuit breaker (gateway/app/services/circuit_breaker.py).

Validates:
  - CLOSED state allows calls through
  - CLOSED → OPEN after failure_threshold failures
  - OPEN rejects calls with CircuitBreakerOpen
  - OPEN → HALF_OPEN after recovery window
  - HALF_OPEN → CLOSED after success_threshold successes
  - HALF_OPEN → OPEN on probe failure
  - Manual reset
  - Timeout handling
"""
import pytest
import asyncio
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState


@pytest.fixture
def cb():
    return CircuitBreaker(
        failure_threshold=3,
        recovery_window_s=1,  # Short for testing
        success_threshold=2,
        name="test",
    )


class TestCircuitBreakerClosed:
    @pytest.mark.asyncio
    async def test_successful_call_passes(self, cb):
        async def ok(): return 42
        result = await cb.call(ok)
        assert result == 42
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_single_failure_stays_closed(self, cb):
        async def fail(): raise ValueError("boom")
        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self, cb):
        async def fail(): raise ValueError("boom")
        async def ok(): return 1
        with pytest.raises(ValueError):
            await cb.call(fail)
        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.failure_count == 2
        await cb.call(ok)
        assert cb.failure_count == 0


class TestCircuitBreakerTransitions:
    @pytest.mark.asyncio
    async def test_closed_to_open_after_threshold(self, cb):
        async def fail(): raise ValueError("boom")
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self, cb):
        async def fail(): raise ValueError("boom")
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)
        with pytest.raises(CircuitBreakerOpen):
            async def ok(): return 1
            await cb.call(ok)

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_recovery(self, cb):
        async def fail(): raise ValueError("boom")
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(1.1)  # Recovery window
        async def ok(): return 1
        result = await cb.call(ok)
        # Should transition to HALF_OPEN then start counting successes
        assert result == 1

    @pytest.mark.asyncio
    async def test_half_open_to_closed_after_successes(self, cb):
        async def fail(): raise ValueError("boom")
        async def ok(): return 1
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)
        await asyncio.sleep(1.1)
        await cb.call(ok)
        await cb.call(ok)  # success_threshold=2
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self, cb):
        async def fail(): raise ValueError("boom")
        async def ok(): return 1
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)
        await asyncio.sleep(1.1)
        await cb.call(ok)  # First success in HALF_OPEN
        with pytest.raises(ValueError):
            await cb.call(fail)  # Failure in HALF_OPEN → back to OPEN
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerTimeout:
    @pytest.mark.asyncio
    async def test_call_with_timeout(self, cb):
        async def slow():
            await asyncio.sleep(5)
            return 1
        with pytest.raises(asyncio.TimeoutError):
            await cb.call(slow, timeout_s=0.1)
        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_fast_call_within_timeout(self, cb):
        async def fast(): return 42
        result = await cb.call(fast, timeout_s=1.0)
        assert result == 42


class TestCircuitBreakerReset:
    @pytest.mark.asyncio
    async def test_manual_reset(self, cb):
        async def fail(): raise ValueError("boom")
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_status_report(self, cb):
        status = cb.status()
        assert status["name"] == "test"
        assert status["state"] == "CLOSED"
        assert status["failure_count"] == 0
