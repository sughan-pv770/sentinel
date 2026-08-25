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

    rule_score, hard_trigger, reasons = await evaluate_rules(ctx, fv, store)
    ml_score = get_ml_engine().score(fv)

    if hard_trigger:
        final_score = max(rule_score, ml_score)
    else:
        final_score = (ML_WEIGHT * ml_score) + (RULE_WEIGHT * rule_score)

    final_score = round(min(final_score, 100.0), 2)
    tier = tier_for_score(final_score, thresholds)
    action = TIER_ACTION[tier]

    if not reasons and ml_score >= 45:
        from app.models import Reason
        reasons.append(Reason(code="anomalous_behaviour_pattern",
                               message=f"Behavioural pattern deviates from this identity's baseline "
                                       f"(ML anomaly score {ml_score:.0f}/100)"))

    return RiskDecision(
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
    )
