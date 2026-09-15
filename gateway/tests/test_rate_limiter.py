"""
Tests for the rate limiter (gateway/app/services/rate_limiter.py).

Validates:
  - Requests within limit pass
  - Request at limit passes, next one triggers exceeded
  - Burst surge (>= ceiling) raises RateLimitExceeded with burst=True
  - Per-IP rate limiting
  - Different identity keys are isolated
"""
import pytest
import asyncio
from app.state_store import InMemoryStore
from app.services.rate_limiter import (
    check_identity_rate,
    check_ip_rate,
    RateLimitExceeded,
)


@pytest.fixture
def store():
    return InMemoryStore()


class TestIdentityRateLimit:
    @pytest.mark.asyncio
    async def test_requests_within_limit_pass(self, store):
        for i in range(10):
            result = await check_identity_rate(
                "u_test", store, window_seconds=60, burst_ceiling=500
            )
            assert not result.exceeded
            assert result.count == i + 1

    @pytest.mark.asyncio
    async def test_burst_surge_raises_exception(self, store):
        """Exactly at ceiling triggers RateLimitExceeded with burst=True."""
        for _ in range(499):
            await check_identity_rate(
                "u_burst", store, window_seconds=60, burst_ceiling=500
            )
        # The 500th request should trigger the burst ceiling
        with pytest.raises(RateLimitExceeded) as exc_info:
            await check_identity_rate(
                "u_burst", store, window_seconds=60, burst_ceiling=500
            )
        assert exc_info.value.burst is True
        assert exc_info.value.count >= 500

    @pytest.mark.asyncio
    async def test_different_identities_are_isolated(self, store):
        """Rate limit state for u_alice should not affect u_bob."""
        for _ in range(10):
            await check_identity_rate("u_alice", store, window_seconds=60, burst_ceiling=500)

        result = await check_identity_rate("u_bob", store, window_seconds=60, burst_ceiling=500)
        assert result.count == 1  # u_bob starts at 1, not 11

    @pytest.mark.asyncio
    async def test_small_burst_ceiling(self, store):
        """Custom lower burst ceiling is respected."""
        for _ in range(4):
            await check_identity_rate("u_small", store, window_seconds=60, burst_ceiling=5)
        with pytest.raises(RateLimitExceeded) as exc:
            await check_identity_rate("u_small", store, window_seconds=60, burst_ceiling=5)
        assert exc.value.burst is True

    @pytest.mark.asyncio
    async def test_window_expiry_resets_count(self, store):
        """After the sliding window expires, count resets."""
        for _ in range(5):
            await check_identity_rate("u_window", store, window_seconds=1, burst_ceiling=500)

        await asyncio.sleep(1.1)  # Wait for window to expire

        result = await check_identity_rate("u_window", store, window_seconds=1, burst_ceiling=500)
        assert result.count == 1  # Reset after window expiry


class TestIPRateLimit:
    @pytest.mark.asyncio
    async def test_ip_within_limit_passes(self, store):
        for i in range(5):
            result = await check_ip_rate("192.168.1.1", store, window_seconds=60, limit=20)
            assert not result.exceeded

    @pytest.mark.asyncio
    async def test_ip_exceeds_limit_raises(self, store):
        for _ in range(20):
            try:
                await check_ip_rate("10.0.0.1", store, window_seconds=60, limit=20)
            except RateLimitExceeded:
                break
        with pytest.raises(RateLimitExceeded) as exc:
            await check_ip_rate("10.0.0.1", store, window_seconds=60, limit=20)
        assert exc.value.burst is False  # IP limit, not identity burst

    @pytest.mark.asyncio
    async def test_different_ips_are_isolated(self, store):
        for _ in range(15):
            await check_ip_rate("1.1.1.1", store, window_seconds=60, limit=20)
        result = await check_ip_rate("2.2.2.2", store, window_seconds=60, limit=20)
        assert result.count == 1
