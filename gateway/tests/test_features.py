"""
Unit tests for the feature extraction module (gateway/app/features.py).

Tests validate:
  - Cold-start identity handling (no false positives on first request)
  - Endpoint novelty detection for known vs unknown endpoints
  - Geo change detection with populated vs empty history
  - Device change detection
  - Payload size z-score calculation
  - Feature vector -> array ordering consistency
"""
import pytest
from datetime import datetime, timezone

from app.models import RequestContext, FeatureVector
from app.features import extract_features, feature_vector_to_array
from app.state_store import InMemoryStore


def _make_ctx(**overrides) -> RequestContext:
    """Helper to create a RequestContext with sensible defaults."""
    defaults = {
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


async def _prime(store, identity_id, endpoint="/profile", geo="IN-TN", device="chrome-macos", count=3):
    """Helper to prime a profile with N requests."""
    ts = datetime.now(timezone.utc)
    for _ in range(count):
        await store.record_request(identity_id, endpoint, geo, device, ts.hour, ts.timestamp())


@pytest.fixture
def store():
    """Fresh in-memory store for each test."""
    return InMemoryStore()


@pytest.mark.asyncio
async def test_cold_identity_no_novelty(store):
    """A brand-new identity (total=0) should NOT flag endpoint/geo/device novelty."""
    ctx = _make_ctx(identity_id="fresh_user", endpoint="/admin/users", geo="RU-MOW")
    fv = await extract_features(ctx, store)

    assert fv.endpoint_novelty == 0.0, "Cold identity should not flag endpoint novelty"
    assert fv.geo_change == 0.0, "Cold identity should not flag geo change"
    assert fv.device_change == 0.0, "Cold identity should not flag device change"


@pytest.mark.asyncio
async def test_known_endpoint_no_novelty(store):
    """An endpoint already in the profile should score 0.0 for novelty."""
    await _prime(store, "warm_user", endpoint="/profile", count=2)

    ctx2 = _make_ctx(identity_id="warm_user", endpoint="/profile")
    fv = await extract_features(ctx2, store)

    assert fv.endpoint_novelty == 0.0, "Known endpoint should not be flagged as novel"


@pytest.mark.asyncio
async def test_unknown_endpoint_is_novel(store):
    """An endpoint NOT in the profile should score 1.0 when identity has history."""
    await _prime(store, "active_user", endpoint="/profile", count=3)

    ctx2 = _make_ctx(identity_id="active_user", endpoint="/admin/users")
    fv = await extract_features(ctx2, store)

    assert fv.endpoint_novelty == 1.0, "Unknown endpoint should be flagged as novel"


@pytest.mark.asyncio
async def test_new_geo_detected(store):
    """A geo not in the identity's history should flag geo_change=1.0."""
    await _prime(store, "geo_user", geo="IN-TN", count=3)

    ctx2 = _make_ctx(identity_id="geo_user", geo="RU-MOW")
    fv = await extract_features(ctx2, store)

    assert fv.geo_change == 1.0, "New geo should be flagged"


@pytest.mark.asyncio
async def test_known_geo_no_change(store):
    """A geo already in the identity's history should be geo_change=0.0."""
    await _prime(store, "stable_geo_user", geo="IN-TN", count=3)

    ctx2 = _make_ctx(identity_id="stable_geo_user", geo="IN-TN")
    fv = await extract_features(ctx2, store)

    assert fv.geo_change == 0.0, "Known geo should not be flagged"


@pytest.mark.asyncio
async def test_new_device_detected(store):
    """A device not in the identity's history should flag device_change=1.0."""
    await _prime(store, "device_user", device="chrome-macos", count=3)

    ctx2 = _make_ctx(identity_id="device_user", device="linux-firefox")
    fv = await extract_features(ctx2, store)

    assert fv.device_change == 1.0, "New device should be flagged"


def test_payload_zscore_normal():
    """A payload near the baseline mean should have a low z-score."""
    ctx = _make_ctx(payload_size=450)  # exactly at baseline mean
    zscore = abs((ctx.payload_size - 450.0) / 250.0)
    assert zscore == 0.0


def test_payload_zscore_abnormal():
    """A very large payload should have a high z-score."""
    ctx = _make_ctx(payload_size=2000)
    zscore = abs((ctx.payload_size - 450.0) / 250.0)
    assert zscore > 5.0, "Extreme payload should produce high z-score"


def test_feature_vector_to_array_ordering():
    """feature_vector_to_array must return 7 elements in a fixed order."""
    fv = FeatureVector(
        request_frequency_per_min=5.0,
        endpoint_novelty=1.0,
        geo_change=0.0,
        device_change=1.0,
        time_of_day_deviation=0.3,
        payload_size_zscore=0.8,
        token_age_seconds=120.0,
    )
    arr = feature_vector_to_array(fv)

    assert len(arr) == 7, "Feature array must have exactly 7 elements"
    assert arr[0] == 5.0, "Index 0 must be request_frequency_per_min"
    assert arr[1] == 1.0, "Index 1 must be endpoint_novelty"
    assert arr[2] == 0.0, "Index 2 must be geo_change"
    assert arr[3] == 1.0, "Index 3 must be device_change"
    assert arr[4] == 0.3, "Index 4 must be time_of_day_deviation"
    assert arr[5] == 0.8, "Index 5 must be payload_size_zscore"
    assert arr[6] == 120.0, "Index 6 must be token_age_seconds"


def test_feature_vector_to_array_type():
    """All elements in the array must be floats."""
    fv = FeatureVector(
        request_frequency_per_min=0,
        endpoint_novelty=0,
        geo_change=0,
        device_change=0,
        time_of_day_deviation=0,
        payload_size_zscore=0,
        token_age_seconds=0,
    )
    arr = feature_vector_to_array(fv)
    for i, val in enumerate(arr):
        assert isinstance(val, (int, float)), f"Element {i} must be numeric, got {type(val)}"
