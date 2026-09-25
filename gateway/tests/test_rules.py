"""
Unit tests for the rule evaluation layer (gateway/app/rules.py).

Tests validate:
  - Token revocation detection (hard-circuit to score 100)
  - Impossible travel trigger (geo change + sufficient history)
  - Impossible travel suppression on cold identities
  - Privilege escalation detection on sensitive endpoints
  - Frequency spike detection
  - Device + geo simultaneous change bonus
  - Score capping at 100
  - Clean identity produces zero rule score
"""
import pytest
from datetime import datetime, timezone

from app.models import RequestContext, FeatureVector
from app.rules import evaluate_rules
from app.state_store import InMemoryStore


def _make_ctx(**overrides) -> RequestContext:
    defaults = {
        "service": "orbit",
        "identity_id": "test_user",
        "session_id": "sess_001",
        "endpoint": "/profile",
        "method": "GET",
        "ip": "127.0.0.1",
        "geo": "IN-TN",
        "device": "chrome-macos",
        "token_age_seconds": 600.0,
        "payload_size": 300,
        "timestamp": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return RequestContext(**defaults)


def _make_fv(**overrides) -> FeatureVector:
    defaults = {
        "request_frequency_per_min": 2.0,
        "endpoint_novelty": 0.0,
        "geo_change": 0.0,
        "device_change": 0.0,
        "time_of_day_deviation": 0.0,
        "payload_size_zscore": 0.2,
        "token_age_seconds": 600.0,
    }
    defaults.update(overrides)
    return FeatureVector(**defaults)


async def _prime(store, identity_id, endpoint="/profile", geo="IN-TN", device="chrome-macos", count=3):
    ts = datetime.now(timezone.utc)
    for _ in range(count):
        await store.record_request(identity_id, endpoint, geo, device, ts.hour, ts.timestamp())


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.mark.asyncio
async def test_revoked_token_returns_100(store):
    """A revoked session must instantly return score=100 with hard trigger."""
    await store.revoke_session("sess_revoked")

    ctx = _make_ctx(session_id="sess_revoked")
    fv = _make_fv()

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert score == 100.0, "Revoked token must produce score 100"
    assert triggered is True, "Revoked token must set hard_trigger"
    assert any(r.code == "token_used_after_revocation" for r in reasons)


@pytest.mark.asyncio
async def test_impossible_travel_with_history(store):
    """Geo change with total >= 3 must trigger impossible_travel."""
    await _prime(store, "traveller", geo="IN-TN", count=3)

    ctx_attack = _make_ctx(identity_id="traveller", geo="RU-MOW")
    fv = _make_fv(geo_change=1.0)

    score, triggered, reasons = await evaluate_rules(ctx_attack, fv, store)

    assert triggered is True, "Geo change with history should trigger"
    assert score >= 55, "Impossible travel adds at least 55 to score"
    assert any(r.code == "impossible_travel" for r in reasons)


@pytest.mark.asyncio
async def test_impossible_travel_suppressed_on_cold_identity(store):
    """Geo change with total < 3 should NOT trigger impossible_travel."""
    await _prime(store, "cold_traveller", geo="IN-TN", count=1)

    ctx2 = _make_ctx(identity_id="cold_traveller", geo="RU-MOW")
    fv = _make_fv(geo_change=1.0)

    score, triggered, reasons = await evaluate_rules(ctx2, fv, store)

    assert not any(r.code == "impossible_travel" for r in reasons), \
        "Cold identity (total < 3) should not fire impossible_travel"


@pytest.mark.asyncio
async def test_privilege_escalation_on_admin_endpoint(store):
    """First-ever access to /admin/* with endpoint_novelty=1 must trigger."""
    await _prime(store, "priv_user", endpoint="/profile", count=3)

    ctx = _make_ctx(identity_id="priv_user", endpoint="/admin/users", service="demo-service")
    fv = _make_fv(endpoint_novelty=1.0)

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert triggered is True, "Privilege escalation should trigger"
    assert score >= 50, "Sensitive endpoint access adds 45+ points"
    assert any(r.code in ("privilege_escalation_attempt", "sensitive_endpoint_access") for r in reasons)


@pytest.mark.asyncio
async def test_privilege_escalation_not_on_normal_endpoint(store):
    """A novel endpoint that is NOT admin/payments should NOT trigger privilege escalation."""
    await _prime(store, "normal_user", endpoint="/profile", count=3)

    ctx = _make_ctx(identity_id="normal_user", endpoint="/orders")
    fv = _make_fv(endpoint_novelty=1.0)

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert not any(r.code == "privilege_escalation_attempt" for r in reasons), \
        "Non-admin endpoint should not fire privilege escalation"


@pytest.mark.asyncio
async def test_payments_endpoint_triggers_escalation(store):
    """The /payments prefix should also be considered sensitive."""
    await _prime(store, "pay_user", endpoint="/profile", count=3)

    ctx = _make_ctx(identity_id="pay_user", endpoint="/payments/transfer", service="demo-service")
    fv = _make_fv(endpoint_novelty=1.0)

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert any(r.code in ("privilege_escalation_attempt", "sensitive_endpoint_access") for r in reasons), \
        "/payments must be treated as sensitive"


@pytest.mark.asyncio
async def test_frequency_spike_detection(store):
    """Request frequency >= 30/min should trigger frequency_spike."""
    ctx = _make_ctx()
    fv = _make_fv(request_frequency_per_min=35.0)

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert score >= 35, "Frequency spike adds 35 to score"
    assert any(r.code == "frequency_spike" for r in reasons)


@pytest.mark.asyncio
async def test_no_frequency_spike_below_threshold(store):
    """Request frequency below 30/min should NOT trigger frequency_spike."""
    ctx = _make_ctx()
    fv = _make_fv(request_frequency_per_min=10.0)

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert not any(r.code == "frequency_spike" for r in reasons)


@pytest.mark.asyncio
async def test_device_and_geo_change_bonus(store):
    """Simultaneous device + geo change should add bonus score."""
    ctx = _make_ctx()
    fv = _make_fv(device_change=1.0, geo_change=1.0)

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert any(r.code == "device_and_geo_change" for r in reasons), \
        "Simultaneous device + geo change should fire"


@pytest.mark.asyncio
async def test_score_capped_at_100(store):
    """Total rule score must never exceed 100."""
    await _prime(store, "multi_trigger", endpoint="/profile", geo="US-NY", count=5)

    ctx = _make_ctx(identity_id="multi_trigger", endpoint="/admin/secret")
    # All triggers fire: geo_change + endpoint_novelty + device_change + frequency
    fv = _make_fv(
        geo_change=1.0,
        endpoint_novelty=1.0,
        device_change=1.0,
        request_frequency_per_min=50.0,
    )

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert score <= 100.0, f"Score must be capped at 100, got {score}"


@pytest.mark.asyncio
async def test_clean_identity_zero_score(store):
    """A normal request with no alerts should produce score=0."""
    ctx = _make_ctx()
    fv = _make_fv()

    score, triggered, reasons = await evaluate_rules(ctx, fv, store)

    assert score == 0.0, "Clean request should have zero rule score"
    assert triggered is False
    assert len(reasons) == 0
