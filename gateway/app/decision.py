"""
Zero Trust decision engine (§4.5). Blends rule-layer + ML scores into the
final 0-100 risk score, maps it to a policy tier, and resolves the
enforcement action.
"""
from __future__ import annotations
from app.models import RequestContext, FeatureVector, RiskDecision
from app.config import TIER_ACTION
from app.ml_engine import get_ml_engine
from app.rules import evaluate_rules
from app.state_store import BaseStore
from app.intelligence import (
    explain_risk,
    calculate_identity_risk,
    calculate_endpoint_risk,
    handle_cold_start,
    get_behavioral_context
)

# How much weight the ML anomaly score carries vs the rule score when no
# hard trigger fired. When a hard trigger DOES fire, the rule layer wins
# outright (short-circuits), per §4.4.1.
ML_WEIGHT = 0.55
RULE_WEIGHT = 0.45


def tier_for_score(score: float, thresholds: dict) -> str:
    if score <= thresholds.get("allow", 30):
        return "allow"
    if score <= thresholds.get("step_up", 60):
        return "step_up"
    if score <= thresholds.get("restrict", 85):
        return "restrict"
    return "revoke"


async def decide(ctx: RequestContext, fv: FeatureVector, store: BaseStore) -> RiskDecision:
    policy = await store.get_policy()
    thresholds = policy.get("thresholds", {"allow": 30, "step_up": 60, "restrict": 85})

    # Get behavioral profile and recent decisions
    profile = await store.get_profile(ctx.identity_id)
    recent_decisions = await store.get_recent_decisions(ctx.identity_id, limit=10)

    rule_score, hard_trigger, reasons = await evaluate_rules(ctx, fv, store)
    ml_score = get_ml_engine().score(fv)

    if hard_trigger:
        final_score = max(rule_score, ml_score)
    else:
        final_score = (ML_WEIGHT * ml_score) + (RULE_WEIGHT * rule_score)

    final_score = round(min(final_score, 100.0), 2)
    tier = tier_for_score(final_score, thresholds)
    action = TIER_ACTION[tier]

    # Generate enhanced explanations using intelligence layer
    if not reasons and ml_score >= 45:
        from app.models import Reason
        reasons.append(Reason(code="anomalous_behaviour_pattern",
                               message=f"Behavioural pattern deviates from this identity's baseline "
                                       f"(ML anomaly score {ml_score:.0f}/100)"))

    # Add detailed risk explanations
    explanations = explain_risk(ctx, fv, ml_score, rule_score, reasons, profile)

    # Calculate identity and endpoint risk
    identity_risk_score, identity_risk_level = calculate_identity_risk(profile, recent_decisions)
    endpoint_risk_score, endpoint_sensitivity = calculate_endpoint_risk(ctx.endpoint)

    # Handle cold start cases
    cold_start_info = handle_cold_start(ctx, profile)

    # Get behavioral context
    behavioral_context = get_behavioral_context(ctx, profile)

    from app.features import feature_vector_to_array
    feature_arr = feature_vector_to_array(fv)

    decision = RiskDecision(
        identity_id=ctx.identity_id,
        session_id=ctx.session_id,
        endpoint=ctx.endpoint,
        risk_score=final_score,
        tier=tier,
        action=action,
        reasons=reasons,
        rule_triggered=hard_trigger,
        ml_score=ml_score,
        rule_score=rule_score,
        features=feature_arr,
        feature_details=fv.model_dump(),
    )

    # Record decision for future analysis
    await store.record_decision(ctx.identity_id, {
        "risk_score": final_score,
        "tier": tier,
        "ml_score": ml_score,
        "rule_score": rule_score,
        "timestamp": ctx.timestamp.isoformat(),
        "endpoint": ctx.endpoint
    })

    return decision
