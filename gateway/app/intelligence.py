"""
Security Intelligence Layer - Enhanced Risk Analysis & Explanations

Provides:
- Enhanced risk explanations
- Identity risk scoring
- Endpoint risk scoring
- Behavioral baseline analysis
- Cold-start handling
"""
from __future__ import annotations
from typing import Dict, List, Tuple
from datetime import datetime, timezone
from app.models import RequestContext, FeatureVector, Reason


def explain_risk(
    ctx: RequestContext,
    fv: FeatureVector,
    ml_score: float,
    rule_score: float,
    reasons: List[Reason],
    profile: Dict
) -> List[str]:
    """
    Generate human-readable risk explanations from raw scores and features.
    Returns a list of explanation strings.
    """
    explanations = []

    # High-level reason from rules
    if reasons:
        for reason in reasons:
            explanations.append(reason.message)

    # ML anomaly explanation
    if ml_score >= 45:
        explanations.append(
            f"Behavioral pattern deviates significantly from baseline (ML anomaly score: {ml_score:.0f}/100)"
        )

    # Feature-level explanations
    if fv.request_frequency_per_min > 20:
        explanations.append(
            f"Unusually high request frequency: {fv.request_frequency_per_min:.1f} req/min"
        )

    if fv.endpoint_novelty > 0 and profile.get("total", 0) > 5:
        explanations.append(
            f"First-time access to endpoint '{ctx.endpoint}' after {profile.get('total')} previous requests"
        )

    if fv.geo_change > 0 and profile.get("total", 0) > 3:
        explanations.append(
            f"Geographic location '{ctx.geo}' not seen in prior activity"
        )

    if fv.device_change > 0 and profile.get("total", 0) > 3:
        explanations.append(
            f"Device fingerprint '{ctx.device}' differs from historical pattern"
        )

    if fv.token_age_seconds < 60:
        explanations.append(
            f"Freshly issued token (age: {int(fv.token_age_seconds)}s) used immediately"
        )
    elif fv.token_age_seconds > 7200:
        explanations.append(
            f"Token is aging (age: {int(fv.token_age_seconds / 3600)}h)"
        )

    if fv.payload_size_zscore > 2.5:
        explanations.append(
            f"Payload size ({ctx.payload_size} bytes) significantly deviates from normal"
        )

    if not explanations:
        explanations.append("Request matches expected behavioral pattern")

    return explanations


def calculate_identity_risk(profile: Dict, recent_decisions: List[Dict]) -> Tuple[float, str]:
    """
    Calculate overall risk score for an identity based on historical behavior.

    Returns: (risk_score 0-100, risk_level string)
    """
    risk_score = 0.0
    total_requests = profile.get("total", 0)

    # Cold start - minimal risk until we have data
    if total_requests < 5:
        return 0.0, "UNKNOWN"

    # Recent decision analysis
    if recent_decisions:
        recent_count = len(recent_decisions)
        high_risk_count = sum(1 for d in recent_decisions if d.get("risk_score", 0) > 60)

        if high_risk_count > 0:
            risk_ratio = high_risk_count / recent_count
            risk_score += risk_ratio * 40

    # Endpoint diversity (accessing many different endpoints rapidly can be suspicious)
    endpoints = profile.get("endpoints", {})
    if len(endpoints) > 10 and total_requests < 50:
        risk_score += 15

    # Geographic diversity (too many locations too quickly)
    geos = profile.get("geos", {})
    if len(geos) > 5:
        risk_score += 10

    # Device diversity (multiple devices rapidly)
    devices = profile.get("devices", {})
    if len(devices) > 3:
        risk_score += 10

    # Cap at 100
    risk_score = min(risk_score, 100.0)

    # Determine risk level
    if risk_score < 30:
        risk_level = "LOW"
    elif risk_score < 60:
        risk_level = "MEDIUM"
    elif risk_score < 85:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    return round(risk_score, 2), risk_level


def calculate_endpoint_risk(ctx: RequestContext) -> Tuple[float, str]:
    """
    Calculate inherent risk score for an endpoint based on sensitivity.
    Returns: (risk_score 0-100, sensitivity_level string)
    """
    from app.service_registry import get_endpoint_sensitivity
    sensitivity = get_endpoint_sensitivity(ctx.service, ctx.endpoint, ctx.method)

    if sensitivity == "admin":
        return 90.0, "CRITICAL"
    if sensitivity == "sensitive":
        return 75.0, "HIGH"
    
    # Read-only endpoints logic can stay if it's not configured in json, 
    # but "normal" is standard
    endpoint_lower = ctx.endpoint.lower()
    if any(prefix in endpoint_lower for prefix in ["/health", "/status", "/public"]):
        return 10.0, "LOW"

    return 30.0, "MODERATE"


def handle_cold_start(ctx: RequestContext, profile: Dict) -> Dict:
    """
    Safely handle new users with insufficient historical data.

    Returns enhanced context with cold-start flags.
    """
    total_requests = profile.get("total", 0)

    cold_start_info = {
        "is_cold_start": total_requests < 5,
        "requests_until_baseline": max(0, 5 - total_requests),
        "confidence_level": "LOW" if total_requests < 5 else "MEDIUM" if total_requests < 20 else "HIGH",
        "baseline_sufficient": total_requests >= 10
    }

    return cold_start_info


def get_behavioral_context(ctx: RequestContext, profile: Dict) -> Dict:
    """
    Generate a comprehensive behavioral context summary for an identity.
    """
    total = profile.get("total", 0)
    endpoints = profile.get("endpoints", {})
    geos = profile.get("geos", {})
    devices = profile.get("devices", {})

    return {
        "total_requests": total,
        "unique_endpoints": len(endpoints),
        "most_common_endpoint": max(endpoints.items(), key=lambda x: x[1])[0] if endpoints else None,
        "unique_geos": len(geos),
        "primary_geo": max(geos.items(), key=lambda x: x[1])[0] if geos else None,
        "unique_devices": len(devices),
        "primary_device": max(devices.items(), key=lambda x: x[1])[0] if devices else None,
        "is_established": total >= 10,
        "behavior_stability": "STABLE" if len(geos) <= 2 and len(devices) <= 2 else "VARIABLE"
    }
