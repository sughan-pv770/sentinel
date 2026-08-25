"""
Rule layer (§4.4.1 of the master doc): deterministic, explainable, always-on.
These can short-circuit straight to a high score regardless of the ML output.
"""
from __future__ import annotations
from app.models import RequestContext, FeatureVector, Reason
from app.state_store import BaseStore

ADMIN_PREFIXES = ("/admin", "/payments")


async def evaluate_rules(ctx: RequestContext, fv: FeatureVector, store: BaseStore) -> tuple[float, bool, list[Reason]]:
    """Returns (rule_score 0-100, hard_trigger_fired, reasons)."""
    reasons: list[Reason] = []
    hard_trigger = False
    score = 0.0

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
        score += 55
        hard_trigger = True

    # 3. Privilege escalation attempt: never-seen admin/payments endpoint
    is_sensitive = ctx.endpoint.startswith(ADMIN_PREFIXES)
    if is_sensitive and fv.endpoint_novelty:
        reasons.append(Reason(code="privilege_escalation_attempt",
                               message=f"First-ever access to sensitive endpoint '{ctx.endpoint}' from this identity"))
        score += 60
        hard_trigger = True

    # 4. Frequency spike -- hard rule kicks in above 6x a "normal" burst (10/min)
    if fv.request_frequency_per_min >= 30:
        reasons.append(Reason(code="frequency_spike",
                               message=f"Request frequency {int(fv.request_frequency_per_min)}/min is far above a normal burst"))
        score += 35

    # 5. Device fingerprint changed mid-session-ish alongside geo change
    if fv.device_change and fv.geo_change:
        reasons.append(Reason(code="device_and_geo_change",
                               message="Device fingerprint and source geo both changed simultaneously"))
        score += 20

    return min(score, 100.0), hard_trigger, reasons
