"""
Rule layer: deterministic, explainable, always-on.
These can short-circuit straight to a high score regardless of ML output.

Rules (in evaluation order):
  1. JTI revocation check          → 100, hard trigger
  2. Session token revocation      → 100, hard trigger
  3. Impossible travel             → +70, hard trigger
  4. Sensitive endpoint (non-privileged) → +45-55, hard trigger
  5. Frequency spike (>= 30/min)   → +35
  6. Device + geo simultaneous change → +20
  7. Rate burst surge (>= 500/min) → 100, hard trigger (pre-empted by middleware,
                                     this catches scenarios the middleware missed)
"""
from __future__ import annotations
from app.models import RequestContext, FeatureVector, Reason
from app.state_store import BaseStore

SENSITIVE_PREFIXES = ("/admin", "/payments")
PRIVILEGED_ROLES = {"admin", "service"}


def _is_privileged(profile: dict, ctx: RequestContext) -> bool:
    role = profile.get("role", "student")
    if role in PRIVILEGED_ROLES:
        return True
    if ctx.identity_id in ("u_admin", "admin") or ctx.identity_id.startswith("u_admin"):
        return True
    return False


async def evaluate_rules(
    ctx: RequestContext, fv: FeatureVector, store: BaseStore
) -> tuple[float, bool, list[Reason]]:
    """Returns (rule_score 0-100, hard_trigger_fired, reasons)."""
    reasons: list[Reason] = []
    hard_trigger = False
    score = 0.0

    # 1. JTI revocation (individual token blacklist)
    if ctx.jti and await store.is_jti_revoked(ctx.jti):
        reasons.append(Reason(
            code="token_used_after_revocation",
            message="JWT token (JTI) was used after being individually revoked",
        ))
        return 100.0, True, reasons

    # 2. Session token revocation
    if await store.is_revoked(ctx.session_id):
        reasons.append(Reason(
            code="token_used_after_revocation",
            message="Session token was used after being revoked",
        ))
        return 100.0, True, reasons

    # 3. Impossible travel
    profile = await store.get_profile(ctx.identity_id)
    if fv.geo_change and profile.get("total", 0) >= 3:
        reasons.append(Reason(
            code="impossible_travel",
            message=f"Source geo '{ctx.geo}' never seen before for this identity, "
                    f"appearing after {profile.get('total')} prior requests from other regions",
        ))
        score += 70
        hard_trigger = True

    # 4. Sensitive endpoint access by non-privileged identity
    is_sensitive = any(ctx.endpoint.startswith(p) for p in SENSITIVE_PREFIXES)
    privileged = _is_privileged(profile, ctx)

    if is_sensitive and not privileged:
        reasons.append(Reason(
            code="sensitive_endpoint_access",
            message=f"Non-privileged identity '{ctx.identity_id}' (role: {profile.get('role', 'student')}) "
                    f"accessing sensitive endpoint '{ctx.endpoint}' — step-up verification required",
        ))
        score += 45
        hard_trigger = True

        if fv.endpoint_novelty:
            reasons.append(Reason(
                code="first_time_sensitive_access",
                message=f"First-ever access to '{ctx.endpoint}' — no prior history for this identity",
            ))
            score += 10

    # 5. Frequency spike (moderate — hard surge handled by middleware)
    if 30 <= fv.request_frequency_per_min < 500:
        reasons.append(Reason(
            code="frequency_spike",
            message=f"Request frequency {int(fv.request_frequency_per_min)}/min is far above a normal burst",
        ))
        score += 35

    # 6. Device fingerprint + geo change simultaneously
    if fv.device_change and fv.geo_change:
        reasons.append(Reason(
            code="device_and_geo_change",
            message="Device fingerprint and source geo both changed simultaneously",
        ))
        score += 20

    # 7. Rate burst surge — hard ceiling (defence-in-depth: middleware catches first)
    if fv.request_frequency_per_min >= 500:
        reasons.append(Reason(
            code="rate_burst_surge",
            message=f"Request rate {int(fv.request_frequency_per_min)}/min exceeds the "
                    f"hard burst ceiling of 500 — session is being terminated",
        ))
        return 100.0, True, reasons

    return min(score, 100.0), hard_trigger, reasons
