"""
Dashboard API Router — /api/dashboard/*

Aggregated data endpoints serving both the Student and Admin portals.
All endpoints require authentication. Admin endpoints additionally
require admin or manager role.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from app.auth import get_current_user, require_role
from app.state_store import get_store
from app.incidents import IncidentManager

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ─── Student Endpoints ────────────────────────────────────────────────────────

@router.get("/student/overview")
async def student_overview(current_user: dict = Depends(get_current_user)):
    """
    Returns a personal risk summary for the authenticated student.
    Accessible by any authenticated role (students see their own data).
    """
    store = get_store()
    identity_id = current_user["identity_id"]

    risk_state = await store.get_risk_state(identity_id)
    profile = await store.get_profile(identity_id)
    recent_decisions = await store.get_recent_decisions(identity_id, limit=20)

    # Compute trend from last 10 decisions
    scores = [d.get("risk_score", 0) for d in recent_decisions]
    trend = "stable"
    if len(scores) >= 3:
        avg_recent = sum(scores[:3]) / 3
        avg_older = sum(scores[3:min(8, len(scores))]) / max(len(scores[3:8]), 1)
        if avg_recent > avg_older + 10:
            trend = "rising"
        elif avg_recent < avg_older - 10:
            trend = "falling"

    # Count alerts for this identity
    all_alerts = await store.get_alerts(limit=200)
    my_alerts = [a for a in all_alerts if a.get("identity_id") == identity_id]

    return {
        "identity_id": identity_id,
        "name": current_user.get("name"),
        "role": current_user.get("role"),
        "risk_score": risk_state.get("risk_score", 0),
        "tier": risk_state.get("tier", "allow"),
        "trend": trend,
        "total_requests": profile.get("total", 0),
        "unique_endpoints": len(profile.get("endpoints", {})),
        "alert_count": len(my_alerts),
        "recent_decisions": recent_decisions[:10],
        "primary_geo": max(profile.get("geos", {}).items(), key=lambda x: x[1])[0]
            if profile.get("geos") else "Unknown",
        "primary_device": max(profile.get("devices", {}).items(), key=lambda x: x[1])[0]
            if profile.get("devices") else "Unknown",
    }


@router.get("/student/activity")
async def student_activity(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Paginated activity log for the authenticated student."""
    store = get_store()
    identity_id = current_user["identity_id"]
    decisions = await store.get_recent_decisions(identity_id, limit=limit)

    # Enrich with tier coloring
    def tier_color(tier):
        return {"allow": "green", "step_up": "amber", "restrict": "orange", "revoke": "red"}.get(tier, "gray")

    return {
        "identity_id": identity_id,
        "activity": [
            {**d, "color": tier_color(d.get("tier", "allow"))}
            for d in decisions
        ],
        "total_shown": len(decisions),
    }


@router.get("/student/risk-profile")
async def student_risk_profile(current_user: dict = Depends(get_current_user)):
    """Returns the 7-signal behavioral baseline for the student's radar chart."""
    store = get_store()
    identity_id = current_user["identity_id"]
    profile = await store.get_profile(identity_id)
    risk_state = await store.get_risk_state(identity_id)

    features = risk_state.get("feature_details") or {}

    return {
        "identity_id": identity_id,
        "profile": {
            "total_requests": profile.get("total", 0),
            "endpoints": dict(list(profile.get("endpoints", {}).items())[:10]),
            "geos": profile.get("geos", {}),
            "devices": profile.get("devices", {}),
        },
        "last_features": features,
        "confidence": (
            "HIGH" if profile.get("total", 0) >= 20
            else "MEDIUM" if profile.get("total", 0) >= 5
            else "LOW"
        ),
    }


# ─── Admin Endpoints ──────────────────────────────────────────────────────────

@router.get("/admin/overview")
async def admin_overview(
    _: dict = Depends(require_role("admin", "manager")),
):
    """
    Aggregated security metrics for the admin Command Center.
    KPI cards: total identities, open incidents, critical alerts, avg risk score.
    """
    store = get_store()
    stats = await store.stats()
    incident_stats = await store.get_incident_stats()
    all_alerts = await store.get_alerts(limit=200)
    users = await store.list_users()

    # Compute average risk score across all tracked identities
    risk_scores = []
    for user in users:
        uid = user["identity_id"]
        state = await store.get_risk_state(uid)
        score = state.get("risk_score", 0)
        if score > 0:
            risk_scores.append(score)

    avg_risk = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0
    high_risk_count = sum(1 for s in risk_scores if s >= 60)

    # Alert breakdown by tier
    tier_counts = defaultdict(int)
    for alert in all_alerts:
        tier_counts[alert.get("tier", "unknown")] += 1

    return {
        "stats": stats,
        "incidents": incident_stats,
        "users_total": len(users),
        "users_by_role": {
            role: sum(1 for u in users if u.get("role") == role)
            for role in ["student", "manager", "admin", "service"]
        },
        "alerts_total": len(all_alerts),
        "alerts_by_tier": dict(tier_counts),
        "avg_risk_score": avg_risk,
        "high_risk_identities": high_risk_count,
        "system_health": "HEALTHY" if avg_risk < 50 else "ELEVATED" if avg_risk < 75 else "CRITICAL",
    }


@router.get("/admin/analytics")
async def admin_analytics(
    _: dict = Depends(require_role("admin", "manager")),
):
    """
    Time-series and distribution analytics for the Threat Analytics page.
    """
    store = get_store()
    users = await store.list_users()
    all_alerts = await store.get_alerts(limit=200)

    # Per-identity risk scores for distribution
    identity_risks = []
    for user in users:
        uid = user["identity_id"]
        state = await store.get_risk_state(uid)
        decisions = await store.get_recent_decisions(uid, limit=20)
        identity_risks.append({
            "identity_id": uid,
            "name": user.get("name", uid),
            "role": user.get("role"),
            "current_risk": state.get("risk_score", 0),
            "tier": state.get("tier", "allow"),
            "request_count": len(decisions),
            "avg_risk": round(
                sum(d.get("risk_score", 0) for d in decisions) / len(decisions), 1
            ) if decisions else 0,
        })

    # Endpoint frequency from alerts
    endpoint_counts = defaultdict(int)
    for alert in all_alerts:
        ep = alert.get("endpoint", "unknown")
        endpoint_counts[ep] += 1

    # Threat type breakdown
    tier_breakdown = defaultdict(int)
    for alert in all_alerts:
        tier_breakdown[alert.get("tier", "unknown")] += 1

    # Geo breakdown from alerts
    geo_counts = defaultdict(int)
    for alert in all_alerts:
        reasons = alert.get("reasons", [])
        for r in reasons:
            msg = r.get("message", "") if isinstance(r, dict) else str(r)
            if "RU" in msg or "russia" in msg.lower():
                geo_counts["RU"] += 1
            elif "IN" in msg:
                geo_counts["IN"] += 1

    return {
        "identity_risks": sorted(identity_risks, key=lambda x: x["current_risk"], reverse=True),
        "top_endpoints": sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        "tier_breakdown": dict(tier_breakdown),
        "geo_threat_counts": dict(geo_counts),
    }


@router.get("/admin/incidents")
async def admin_incidents(
    limit: int = 50,
    severity: str = None,
    _: dict = Depends(require_role("admin", "manager")),
):
    """Incidents list with optional severity filter."""
    store = get_store()
    incidents = await store.get_incidents(limit=limit, severity=severity)
    stats = await store.get_incident_stats()
    return {"incidents": incidents, "stats": stats}


@router.get("/admin/live-feed")
async def admin_live_feed(
    limit: int = 100,
    _: dict = Depends(require_role("admin", "manager")),
):
    """
    Combined live feed of alerts + incidents for the Command Center.
    Returns the most recent security events across all identities.
    """
    store = get_store()
    alerts = await store.get_alerts(limit=limit)
    incidents = await store.get_incidents(limit=20)

    return {
        "alerts": alerts,
        "incidents": incidents,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
