"""
Zero Trust decision engine. Blends rule-layer + ML scores into the
final 0-100 risk score, maps it to a policy tier, and resolves the
enforcement action.

Production enhancements vs. prototype:
  - ML inference wrapped in asyncio circuit breaker + 50ms timeout SLA
  - Shadow mode: score ML without affecting decision (SENTINELX_ML_SHADOW=true)
  - mfa_required + mfa_method populated on RiskDecision
  - revoke tier triggers revoke_all_sessions + SSE broadcast
"""
from __future__ import annotations
import asyncio
import time
from app.models import RequestContext, FeatureVector, RiskDecision
from app.config import TIER_ACTION, settings
from app.rules import evaluate_rules
from app.state_store import BaseStore
from app.intelligence import (
    explain_risk,
    calculate_identity_risk,
    calculate_endpoint_risk,
    handle_cold_start,
    get_behavioral_context,
)
from app.services.circuit_breaker import get_ml_circuit_breaker, CircuitBreakerOpen
from app.services.mfa_service import mfa_method_for_risk
from app.utils.logger import get_logger

logger = get_logger("sentinelx.decision")

ML_WEIGHT = 0.55
RULE_WEIGHT = 0.45

# Fallback ML score when circuit is OPEN (neutral — rule layer governs alone)
ML_FALLBACK_SCORE = 50.0


def tier_for_score(score: float, thresholds: dict) -> str:
    if score <= thresholds.get("allow", 30):
        return "allow"
    if score <= thresholds.get("step_up", 60):
        return "step_up"
    if score <= thresholds.get("restrict", 85):
        return "restrict"
    return "revoke"


async def _score_ml_async(fv: FeatureVector) -> float:
    """Wrap synchronous ML scoring as an awaitable for timeout / circuit breaker."""
    from app.ml_engine import get_ml_engine
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_ml_engine().score, fv)


async def decide(ctx: RequestContext, fv: FeatureVector, store: BaseStore) -> RiskDecision:
    policy = await store.get_policy()
    thresholds = policy.get("thresholds", {"allow": 30, "step_up": 60, "restrict": 85})

    profile = await store.get_profile(ctx.identity_id)
    recent_decisions = await store.get_recent_decisions(ctx.identity_id, limit=10)

    rule_score, hard_trigger, reasons = await evaluate_rules(ctx, fv, store)

    # ── ML inference (circuit breaker + SLA timeout) ───────────────────────────
    ml_timed_out = False
    cb = get_ml_circuit_breaker()
    timeout_s = settings.ml_inference_timeout_ms / 1000.0

    try:
        t_ml = time.perf_counter()
        ml_score = await cb.call(_score_ml_async, fv, timeout_s=timeout_s)
        ml_latency_ms = (time.perf_counter() - t_ml) * 1000

        try:
            from app.observability import ml_inference_latency_ms
            ml_inference_latency_ms.observe(ml_latency_ms)
        except Exception:
            pass

    except (CircuitBreakerOpen, asyncio.TimeoutError) as exc:
        ml_score = ML_FALLBACK_SCORE
        ml_timed_out = True
        logger.warning(f"ML inference bypassed  identity={ctx.identity_id}  reason={type(exc).__name__}")

    # ── Shadow mode: score ML but don't use it in the decision ────────────────
    if settings.ml_shadow_mode:
        ml_score = ML_FALLBACK_SCORE

    # ── Blend scores ──────────────────────────────────────────────────────────
    if hard_trigger:
        final_score = max(rule_score, ml_score)
    else:
        final_score = (ML_WEIGHT * ml_score) + (RULE_WEIGHT * rule_score)

    final_score = round(min(final_score, 100.0), 2)
    tier = tier_for_score(final_score, thresholds)
    action = TIER_ACTION[tier]

    # ── ML reason annotation ──────────────────────────────────────────────────
    if not reasons and ml_score >= 45:
        from app.models import Reason
        reasons.append(Reason(
            code="anomalous_behaviour_pattern",
            message=f"Behavioural pattern deviates from this identity's baseline "
                    f"(ML anomaly score {ml_score:.0f}/100)",
        ))

    explanations = explain_risk(ctx, fv, ml_score, rule_score, reasons, profile)
    identity_risk_score, identity_risk_level = calculate_identity_risk(profile, recent_decisions)
    endpoint_risk_score, endpoint_sensitivity = calculate_endpoint_risk(ctx.endpoint)
    cold_start_info = handle_cold_start(ctx, profile)
    behavioral_context = get_behavioral_context(ctx, profile)

    # ── MFA requirement ───────────────────────────────────────────────────────
    mfa_method = mfa_method_for_risk(final_score, policy) if tier == "step_up" else None
    mfa_required = mfa_method is not None

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
        mfa_required=mfa_required,
        mfa_method=mfa_method,
        ml_timed_out=ml_timed_out,
    )

    await store.record_decision(ctx.identity_id, {
        "risk_score": final_score,
        "tier": tier,
        "ml_score": ml_score,
        "rule_score": rule_score,
        "ml_timed_out": ml_timed_out,
        "timestamp": ctx.timestamp.isoformat(),
        "endpoint": ctx.endpoint,
    })

    # ── Update circuit breaker gauge ──────────────────────────────────────────
    try:
        from app.observability import ml_circuit_state
        from app.services.circuit_breaker import CircuitState
        state_map = {CircuitState.CLOSED: 0, CircuitState.HALF_OPEN: 1, CircuitState.OPEN: 2}
        ml_circuit_state.set(state_map.get(cb.state, 0))
    except Exception:
        pass

    return decision
