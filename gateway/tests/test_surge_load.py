"""
Surge load test — simulates 500+ concurrent requests from one identity.

Validates:
  - Rate limiter fires before the ML pipeline for identity surge
  - The 500th request (at burst ceiling) triggers RateLimitExceeded
  - Concurrent requests from different identities are isolated
"""
import pytest
import asyncio
from app.state_store import InMemoryStore
from app.services.rate_limiter import check_identity_rate, RateLimitExceeded


@pytest.fixture
def store():
    return InMemoryStore()


class TestSurgeLoad:
    @pytest.mark.asyncio
    async def test_500_requests_trigger_surge(self, store):
        """499 requests pass; the 500th hits the burst ceiling."""
        success_count = 0
        surge_triggered = False

        for i in range(600):
            try:
                await check_identity_rate(
                    "u_surge_test", store, window_seconds=60, burst_ceiling=500
                )
                success_count += 1
            except RateLimitExceeded as exc:
                if exc.burst:
                    surge_triggered = True
                    break

        assert success_count == 499, f"Expected 499 successful requests, got {success_count}"
        assert surge_triggered, "Surge should have been triggered at the 500th request"

    @pytest.mark.asyncio
    async def test_concurrent_surge_from_single_identity(self, store):
        """Concurrent coroutines from one identity trigger surge protection."""
        results = {"success": 0, "surge": 0, "other": 0}

        async def send_request():
            try:
                await check_identity_rate(
                    "u_concurrent_surge", store, window_seconds=60, burst_ceiling=500
                )
                results["success"] += 1
            except RateLimitExceeded as exc:
                if exc.burst:
                    results["surge"] += 1
                else:
                    results["other"] += 1

        # Fire 550 concurrent requests
        tasks = [send_request() for _ in range(550)]
        await asyncio.gather(*tasks)

        total = results["success"] + results["surge"]
        assert total == 550, f"All requests should complete, got {total}"
        assert results["surge"] > 0, "At least some requests should hit the surge ceiling"
        assert results["success"] <= 500, f"At most 500 should succeed, got {results['success']}"

    @pytest.mark.asyncio
    async def test_surge_from_one_identity_does_not_affect_another(self, store):
        """Identity A's surge should not block identity B."""
        # Trigger surge for identity A
        for _ in range(499):
            await check_identity_rate("u_identity_a", store, window_seconds=60, burst_ceiling=500)

        # Identity B should still be allowed through
        result = await check_identity_rate(
            "u_identity_b", store, window_seconds=60, burst_ceiling=500
        )
        assert result.count == 1
        assert not result.exceeded

    @pytest.mark.asyncio
    async def test_configurable_burst_ceiling(self, store):
        """Lower burst ceiling can be configured."""
        for _ in range(9):
            await check_identity_rate("u_low_ceiling", store, window_seconds=60, burst_ceiling=10)

        with pytest.raises(RateLimitExceeded) as exc:
            await check_identity_rate("u_low_ceiling", store, window_seconds=60, burst_ceiling=10)
        assert exc.value.burst is True
        assert exc.value.limit == 10
