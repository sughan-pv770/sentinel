"""
Per-request feature extraction (§4.2 / §9.2 of the master doc).

Computes the 4-5 signal groups against the caller's rolling profile:
  - request frequency (per minute, vs their own history)
  - endpoint novelty (has this identity ever hit this endpoint before)
  - geo change since last-seen geo distribution
  - device/user-agent change
  - time-of-day deviation from their typical hour-of-day
  - payload size anomaly (z-score against their own history)
"""
from __future__ import annotations
import statistics
from app.models import RequestContext, FeatureVector
from app.state_store import BaseStore


async def extract_features(ctx: RequestContext, store: BaseStore) -> FeatureVector:
    profile = await store.get_profile(ctx.identity_id)
    total = profile.get("total", 0)

    # --- request frequency: requests in the last 60s from this identity ---
    timestamps = profile.get("timestamps", [])
    now = ctx.timestamp.timestamp()
    recent = [t for t in timestamps if now - t <= 60]
    request_frequency_per_min = float(len(recent))

    # --- endpoint novelty ---
    # A totally cold identity (no baseline yet) has nothing to deviate
    # from, so its first request isn't "novel" in a meaningful sense --
    # same cold-start treatment already given to geo/device below.
    endpoints = profile.get("endpoints", {})
    endpoint_novelty = 0.0 if (ctx.endpoint in endpoints or total == 0) else 1.0

    # --- geo change: has this geo ever been seen for this identity ---
    geos = profile.get("geos", {})
    geo_change = 0.0 if (ctx.geo in geos or total == 0) else 1.0

    # --- device change ---
    devices = profile.get("devices", {})
    device_change = 0.0 if (ctx.device in devices or total == 0) else 1.0

    # --- time-of-day deviation ---
    hours = profile.get("hours", [])
    current_hour = ctx.timestamp.hour
    if hours:
        # circular distance in hours to the nearest historical hour bucket
        diffs = [min(abs(current_hour - h), 24 - abs(current_hour - h)) for h in hours]
        time_of_day_deviation = float(min(diffs)) / 12.0  # normalize 0..1
    else:
        time_of_day_deviation = 0.0

    # --- payload size z-score (EWMA approach: if we have enough profile
    #     history, use the stored mean/std; otherwise cold-start fallback) ---
    payload_history = profile.get("payload_sizes", [])
    if len(payload_history) >= 5:
        import statistics
        baseline_mean = statistics.mean(payload_history[-50:])
        baseline_std = max(statistics.stdev(payload_history[-50:]), 50.0)  # floor to avoid /0
    else:
        # Cold-start: use global baseline from training distribution
        baseline_mean, baseline_std = 450.0, 250.0
    payload_size_zscore = abs((ctx.payload_size - baseline_mean) / baseline_std)

    return FeatureVector(
        request_frequency_per_min=request_frequency_per_min,
        endpoint_novelty=endpoint_novelty,
        geo_change=geo_change,
        device_change=device_change,
        time_of_day_deviation=time_of_day_deviation,
        payload_size_zscore=payload_size_zscore,
        token_age_seconds=ctx.token_age_seconds,
    )


def feature_vector_to_array(fv: FeatureVector) -> list[float]:
    """Fixed ordering used consistently by both training and inference."""
    return [
        fv.request_frequency_per_min,
        fv.endpoint_novelty,
        fv.geo_change,
        fv.device_change,
        fv.time_of_day_deviation,
        fv.payload_size_zscore,
        fv.token_age_seconds,
    ]
