"""
Tests for session revocation (JTI blacklist + session-level revocation).

Validates:
  - Revoked session IDs are blocked by is_revoked()
  - JTI revocation blocks individual tokens
  - revoke_all_user_sessions revokes all tracked sessions
  - Revocation audit log is written
  - SSE manager receives broadcast on revocation
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.state_store import InMemoryStore
from app.services.session_service import (
    create_session,
    revoke_session_and_broadcast,
    revoke_all_sessions_and_broadcast,
)


@pytest.fixture
def store():
    return InMemoryStore()


class TestSessionRevocation:
    @pytest.mark.asyncio
    async def test_revoke_blocks_session(self, store):
        assert not await store.is_revoked("sess_abc")
        await store.revoke_session("sess_abc")
        assert await store.is_revoked("sess_abc")

    @pytest.mark.asyncio
    async def test_jti_revocation_blocks_token(self, store):
        jti = "test-jti-001"
        assert not await store.is_jti_revoked(jti)
        await store.revoke_jti(jti, ttl_seconds=3600)
        assert await store.is_jti_revoked(jti)

    @pytest.mark.asyncio
    async def test_jti_expiry(self, store):
        jti = "test-jti-002"
        await store.revoke_jti(jti, ttl_seconds=1)
        assert await store.is_jti_revoked(jti)
        await asyncio.sleep(1.1)
        # Expired TTL should no longer be revoked
        assert not await store.is_jti_revoked(jti)

    @pytest.mark.asyncio
    async def test_register_and_revoke_all(self, store):
        # Register two sessions for the same identity
        await store.register_active_session("u_alice", "sess_a1", "jti_a1")
        await store.register_active_session("u_alice", "sess_a2", "jti_a2")

        sessions = await store.get_active_sessions("u_alice")
        assert len(sessions) == 2

        revoked_ids = await store.revoke_all_user_sessions("u_alice")
        assert "sess_a1" in revoked_ids
        assert "sess_a2" in revoked_ids

        # Both sessions should now be revoked
        assert await store.is_revoked("sess_a1")
        assert await store.is_revoked("sess_a2")
        # Both JTIs should be revoked
        assert await store.is_jti_revoked("jti_a1")
        assert await store.is_jti_revoked("jti_a2")

    @pytest.mark.asyncio
    async def test_revoke_all_clears_session_list(self, store):
        await store.register_active_session("u_bob", "sess_b1", "jti_b1")
        await store.revoke_all_user_sessions("u_bob")
        sessions = await store.get_active_sessions("u_bob")
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_revocation_audit_written(self, store):
        with patch("app.services.session_service.get_sse_manager") as mock_sse:
            mock_sse.return_value.broadcast_termination = AsyncMock(return_value=0)
            audit = await revoke_session_and_broadcast(
                identity_id="u_alice",
                session_id="sess_x",
                jti="jti_x",
                reason="impossible_travel",
                risk_score=87.5,
                triggered_by="rule_engine",
                store=store,
            )

        assert audit["identity_id"] == "u_alice"
        assert audit["reason"] == "impossible_travel"
        assert audit["risk_score"] == 87.5

        audit_log = await store.get_revocation_audit(limit=10)
        assert len(audit_log) >= 1
        assert audit_log[0]["identity_id"] == "u_alice"

    @pytest.mark.asyncio
    async def test_sse_broadcast_called_on_revoke(self, store):
        with patch("app.services.session_service.get_sse_manager") as mock_sse:
            mock_broadcast = AsyncMock(return_value=1)
            mock_sse.return_value.broadcast_termination = mock_broadcast

            await revoke_all_sessions_and_broadcast(
                identity_id="u_charlie",
                reason="rate_burst_surge",
                risk_score=100.0,
                triggered_by="ml_engine",
                store=store,
            )

        mock_broadcast.assert_called_once_with(
            identity_id="u_charlie",
            reason="rate_burst_surge",
            risk_score=100.0,
            triggered_by="ml_engine",
        )


class TestJTIInRules:
    @pytest.mark.asyncio
    async def test_revoked_jti_triggers_hard_rule(self, store):
        """A request using a revoked JTI should score 100 from the rule engine."""
        from app.models import RequestContext, FeatureVector
        from app.rules import evaluate_rules
        from datetime import datetime, timezone

        jti = "revoked-jti-xyz"
        await store.revoke_jti(jti, ttl_seconds=3600)

        ctx = RequestContext(
            identity_id="u_alice", session_id="sess_new",
            endpoint="/profile", method="GET", ip="127.0.0.1",
            geo="IN-TN", device="chrome-macos", token_age_seconds=100,
            payload_size=200, jti=jti,
            timestamp=datetime.now(timezone.utc),
        )
        fv = FeatureVector(
            request_frequency_per_min=1, endpoint_novelty=0, geo_change=0,
            device_change=0, time_of_day_deviation=0, payload_size_zscore=0,
            token_age_seconds=100,
        )
        score, hard_trigger, reasons = await evaluate_rules(ctx, fv, store)
        assert score == 100.0
        assert hard_trigger is True
        assert any("JTI" in r.message or "revocation" in r.message.lower() for r in reasons)
