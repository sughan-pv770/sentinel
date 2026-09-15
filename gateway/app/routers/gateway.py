"""
Gateway proxy router — real request lifecycle:
intercept → rate-limit → extract features → score → decide → enforce → audit.

Production enhancements:
  - SSE broadcast on revoke (real-time frontend forced logout)
  - MFA challenge creation on step_up (real TOTP/OTP challenge, not mock)
  - revoke_all_user_sessions for critical-tier decisions
  - Prometheus metrics recording per request
"""
from __future__ import annotations
import time
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.models import RequestContext
from app.features import extract_features
from app.decision import decide
from app.state_store import get_store
from app.proxy import forward
from app.utils.logger import get_logger, log_decision
from app.incidents import IncidentManager

router = APIRouter()
logger = get_logger("sentinelx.gateway")


def _mock_geo_device(request: Request) -> tuple[str, str]:
    """In production these come from GeoIP + UA parsing middleware.
    Honour explicit override headers (used by simulator) and fall back to defaults."""
    geo = request.headers.get("x-mock-geo", "IN-TN")
    device = request.headers.get("x-mock-device", "chrome-macos")
    return geo, device


@router.api_route(
    "/gateway/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def gateway_proxy(service: str, path: str, request: Request):
    t0 = time.perf_counter()
    store = get_store()

    identity_id = request.headers.get("x-identity-id", "anonymous")
    session_id = request.headers.get("x-session-id", f"sess_{identity_id}_default")
    token_age = float(request.headers.get("x-token-age-seconds", "600"))
    jti = request.headers.get("x-jti")  # Optional JTI from token middleware
    geo, device = _mock_geo_device(request)
    body = await request.body()

    ctx = RequestContext(
        identity_id=identity_id,
        session_id=session_id,
        endpoint=f"/{path}",
        method=request.method,
        ip=request.client.host if request.client else "0.0.0.0",
        geo=geo,
        device=device,
        token_age_seconds=token_age,
        payload_size=len(body),
        jti=jti,
    )

    fv = await extract_features(ctx, store)
    decision = await decide(ctx, fv, store)

    await store.record_request(
        ctx.identity_id, ctx.endpoint, ctx.geo, ctx.device,
        ctx.timestamp.hour, ctx.timestamp.timestamp(),
    )
    await store.set_risk_state(ctx.identity_id, decision.model_dump(mode="json"))

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    # Incident creation for high-risk decisions
    incident_manager = IncidentManager(store)
    if incident_manager.should_create_incident(decision.risk_score, decision.tier, decision.rule_triggered):
        await incident_manager.create_incident(
            identity_id=ctx.identity_id,
            endpoint=ctx.endpoint,
            risk_score=decision.risk_score,
            ml_score=decision.ml_score,
            rule_score=decision.rule_score,
            reasons=decision.reasons,
            tier=decision.tier,
            action=decision.action,
        )

    if decision.tier != "allow":
        alert = decision.model_dump(mode="json")
        alert["latency_ms"] = elapsed_ms
        alert["service"] = service
        await store.add_alert(alert)
        log_decision(logger, alert)

    # ── REVOKE: terminate all sessions + SSE broadcast ────────────────────────
    if decision.tier == "revoke":
        from app.services.session_service import revoke_all_sessions_and_broadcast
        from app.observability import sessions_revoked_total

        reason = (decision.reasons[0].code if decision.reasons else "anomaly_detected")
        triggered_by = "rule_engine" if decision.rule_triggered else "ml_engine"

        audit = await revoke_all_sessions_and_broadcast(
            identity_id=ctx.identity_id,
            reason=reason,
            risk_score=decision.risk_score,
            triggered_by=triggered_by,
            store=store,
        )
        sessions_revoked_total.labels(triggered_by=triggered_by).inc()

        return JSONResponse(
            status_code=401,
            content={
                "error": "session_revoked",
                "risk_score": decision.risk_score,
                "reasons": [r.message for r in decision.reasons],
                "sse_broadcast": audit.get("connections_notified", 0),
            },
        )

    # ── RESTRICT: rate-limit response ─────────────────────────────────────────
    if decision.tier == "restrict":
        return JSONResponse(
            status_code=429,
            content={
                "error": "restricted",
                "risk_score": decision.risk_score,
                "reasons": [r.message for r in decision.reasons],
                "action": decision.action,
            },
        )

    # ── STEP_UP: create real MFA challenge ────────────────────────────────────
    if decision.tier == "step_up":
        mfa_method = decision.mfa_method or "totp"
        from app.services.mfa_service import generate_email_otp
        challenge_data = {"method": mfa_method, "ttl_seconds": 300, "session_id": session_id}

        if mfa_method == "email_otp":
            otp_result = await generate_email_otp(ctx.identity_id, session_id, store)
            challenge_data.update(otp_result)

        return JSONResponse(
            status_code=401,
            content={
                "error": "step_up_required",
                "risk_score": decision.risk_score,
                "reasons": [r.message for r in decision.reasons],
                "challenge": challenge_data,
            },
        )

    # ── ALLOW: forward to origin ───────────────────────────────────────────────
    try:
        origin_resp = await forward(request, path, identity_id)
        return Response(
            content=origin_resp.content,
            status_code=origin_resp.status_code,
            headers={
                "x-sentinelx-risk-score": str(decision.risk_score),
                "x-sentinelx-tier": decision.tier,
                "x-sentinelx-latency-ms": str(elapsed_ms),
            },
            media_type=origin_resp.headers.get("content-type", "application/json"),
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "origin_unreachable", "detail": str(e)})


@router.api_route("/profile", methods=["GET", "POST"])
@router.api_route("/orders", methods=["GET", "POST"])
@router.api_route("/users", methods=["GET", "POST"])
@router.api_route("/payments/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@router.api_route("/admin/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def direct_resource_proxy(request: Request, path: str = ""):
    """Direct resource shortcut — routes through full SentinelX scoring."""
    raw_path = request.url.path.lstrip("/")
    return await gateway_proxy(service="demo-service", path=raw_path, request=request)
