"""
Rule layer (§4.4.1 of the master doc): deterministic, explainable, always-on.
These can short-circuit straight to a high score regardless of the ML output.
"""
from __future__ import annotations
from app.models import RequestContext, FeatureVector, Reason
from app.state_store import BaseStore


# Roles that are expected to access sensitive endpoints routinely.
PRIVILEGED_ROLES = {"admin", "service"}


def _is_privileged(profile: dict, ctx: RequestContext) -> bool:
    """Check if the identity is allowed unrestricted access to sensitive paths."""
    role = profile.get("role", "student")
    if role in PRIVILEGED_ROLES:
        return True
    if ctx.identity_id in ("u_admin", "admin") or ctx.identity_id.startswith("u_admin"):
        return True
    return False


async def evaluate_rules(ctx: RequestContext, fv: FeatureVector, store: BaseStore) -> tuple[float, bool, list[Reason]]:
    """Returns (rule_score 0-100, hard_trigger_fired, reasons)."""
    reasons: list[Reason] = []
    hard_trigger = False
    score = 0.0

    # 0. Identity revoked
    if await store.is_identity_revoked(ctx.identity_id):
        reasons.append(Reason(code="identity_revoked",
                               message="Identity has been revoked and requires admin unlock"))
        return 100.0, True, reasons

    # 1. Token reuse after revocation
    if await store.is_revoked(ctx.session_id):
        reasons.append(Reason(code="token_used_after_revocation",
                               message="Session token was used after being revoked"))
        return 100.0, True, reasons

    # 2. Impossible travel: geo changed AND identity has meaningful history
    profile = await store.get_profile(ctx.identity_id)
    if fv.geo_change and profile.get("total", 0) >= 3:
        reasons.append(Reason(code="impossible_travel",
                               message=f"Source geo '{ctx.geo}' never seen before for this identity, "
                                       f"appearing after {profile.get('total')} prior requests from other regions"))
        score += 70
        hard_trigger = True

    # 3. Sensitive endpoint access by non-privileged identity.
    #    Unlike the old rule which only fired on *first* access (endpoint_novelty),
    #    Zero Trust requires step-up verification EVERY time a student/manager
    #    touches /payments or /admin endpoints.
    from app.service_registry import get_endpoint_sensitivity
    sensitivity = get_endpoint_sensitivity(ctx.service, ctx.endpoint, ctx.method)
    is_sensitive = sensitivity in ("sensitive", "admin")
    privileged = _is_privileged(profile, ctx)

    if is_sensitive and not privileged:
        # Base: sensitive endpoint access from non-privileged role
        reasons.append(Reason(
            code="sensitive_endpoint_access",
            message=f"Non-privileged identity '{ctx.identity_id}' (role: {profile.get('role', 'student')}) "
                    f"accessing sensitive endpoint '{ctx.endpoint}' ({ctx.method}) — step-up verification required"))
        score += 45
        hard_trigger = True

        # Bonus: first-ever access makes it even riskier
        if fv.endpoint_novelty:
            reasons.append(Reason(
                code="first_time_sensitive_access",
                message=f"First-ever access to '{ctx.endpoint}' — no prior history for this identity"))
            score += 10

    # 4. Frequency spike — scales dynamically above 30/min
    if fv.request_frequency_per_min >= 30:
        # 35 base points, plus 1 point for every 2 requests over 30
        added_score = 35 + ((fv.request_frequency_per_min - 30) * 0.5)
        score += added_score
        reasons.append(Reason(code="frequency_spike",
                               message=f"Request frequency {int(fv.request_frequency_per_min)}/min is far above a normal burst"))
        
        if fv.request_frequency_per_min >= 60:
            hard_trigger = True

    # 5. Device fingerprint changed mid-session-ish alongside geo change
    if fv.device_change and fv.geo_change:
        reasons.append(Reason(code="device_and_geo_change",
                               message="Device fingerprint and source geo both changed simultaneously"))
        score += 20

    return min(score, 100.0), hard_trigger, reasons
