"""
POST/GET/PUT/DELETE /gateway/{service}/{path:path}

This is the real request lifecycle from §3 of the master doc, steps 2-7:
intercept -> extract features -> read/write behavioural state -> score ->
decide -> enforce (proxy / step-up / restrict / revoke) -> audit log.
"""
from __future__ import annotations
import time
import random
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.models import RequestContext
from app.features import extract_features
from app.decision import decide
from app.state_store import get_store
from app.proxy import forward
from app.utils.logger import get_logger, log_decision
from app.incidents import IncidentManager
from app.service_registry import is_auth_required, get_upstream_url
from collections import defaultdict
import secrets

_rate_limits = defaultdict(list)

def check_rate_limit(identity_id: str, max_requests: int = 100, window_sec: int = 60) -> bool:
    now = time.time()
    _rate_limits[identity_id] = [t for t in _rate_limits[identity_id] if now - t < window_sec]
    if len(_rate_limits[identity_id]) >= max_requests:
        return False
    _rate_limits[identity_id].append(now)
    return True

router = APIRouter()
logger = get_logger("sentinelx.gateway")


def _mock_geo_device(request: Request) -> tuple[str, str]:
    """In production these come from GeoIP + UA parsing middleware. For the
    demo, honour explicit override headers (used by the simulator/dashboard)
    and fall back to sensible defaults for organic curl/browser traffic."""
    geo = request.headers.get("x-mock-geo", "IN-TN")
    device = request.headers.get("x-mock-device", "chrome-macos")
    return geo, device


@router.api_route("/gateway/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway_proxy(service: str, path: str, request: Request):
    t0 = time.perf_counter()
    store = get_store()

    # Pre-auth endpoints (auth_required: false in services.json) bypass
    # identity-based scoring — they're protected by IP rate-limiting only.
    if not is_auth_required(service, path, request.method):
        try:
            origin_resp = await forward(request, service, path, "anonymous")
            return Response(
                content=origin_resp.content,
                status_code=origin_resp.status_code,
                headers={"x-sentinelx-pre-auth": "true"},
                media_type=origin_resp.headers.get("content-type", "application/json"),
            )
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": "origin_unreachable", "detail": str(e)})

    identity_id = request.headers.get("x-identity-id", "anonymous")
    
    from app.config import settings
    is_demo_burst = request.headers.get("x-demo-burst") == "true" and settings.environment != "production"
    
    if not is_demo_burst and not check_rate_limit(identity_id):
        return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded", "message": "Too many requests"})
        
    nonce = request.headers.get("x-nonce")
    if nonce:
        if await store.has_nonce(identity_id, nonce):
            return JSONResponse(status_code=401, content={"error": "replay_detected"})
        await store.store_nonce(identity_id, nonce)
        
    session_id = request.headers.get("x-session-id", f"sess_{identity_id}_default")
    token_age = float(request.headers.get("x-token-age-seconds", "600"))
    geo, device = _mock_geo_device(request)
    body = await request.body()

    ctx = RequestContext(
        service=service,
        identity_id=identity_id,
        session_id=session_id,
        endpoint=f"/{path}",
        method=request.method,
        ip=request.client.host if request.client else "0.0.0.0",
        geo=geo,
        device=device,
        token_age_seconds=token_age,
        payload_size=len(body),
    )

    fv = await extract_features(ctx, store)
    decision = await decide(ctx, fv, store)

    # Record this request into the behavioural baseline regardless of
    # outcome, so future scoring reflects it (§4.3).
    await store.record_request(ctx.identity_id, ctx.endpoint, ctx.geo, ctx.device, ctx.timestamp.hour, ctx.timestamp.timestamp(), ctx.payload_size)
    await store.set_risk_state(ctx.identity_id, decision.model_dump(mode="json"))

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    # Create incident if risk is high
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
            action=decision.action
        )

    # Add every request to the alerts list so it appears in the Request Ledger
    alert = decision.model_dump(mode="json")
    alert["latency_ms"] = elapsed_ms
    alert["service"] = service
    await store.add_alert(alert)
    log_decision(logger, alert)

    # Collective Immune System: auto-publish threat signal on RESTRICT or REVOKE (0% PII, SHA-256 only)
    if decision.tier in ("restrict", "revoke") and ctx.identity_id != "anonymous":
        import hashlib
        from datetime import datetime, timezone
        from app.config import settings
        id_hash = hashlib.sha256(ctx.identity_id.encode("utf-8")).hexdigest()
        reason_cat = decision.reasons[0].code if decision.reasons else "threat_detected"
        signal = {
            "signal_id": f"sig_{secrets.token_hex(6)}",
            "identity_hash": id_hash,
            "gateway_id": settings.gateway_id,
            "gateway_name": settings.gateway_name,
            "verdict_tier": decision.tier.upper(),
            "severity": "CRITICAL" if decision.tier == "revoke" else "HIGH",
            "reason_category": reason_cat,
            "timestamp": time.time(),
            "iso_time": datetime.now(timezone.utc).isoformat(),
            "is_simulated_peer": False,
        }
        await store.add_threat_signal(signal)

    if decision.tier == "revoke":
        await store.revoke_session(ctx.session_id)
        
        is_identity_revoked_reason = any(r.code == "identity_revoked" for r in decision.reasons)
        if not is_identity_revoked_reason:
            await store.revoke_identity(ctx.identity_id)
            
        error_type = "identity_revoked" if is_identity_revoked_reason else "session_revoked"
        return JSONResponse(
            status_code=401,
            content={"error": error_type, "risk_score": decision.risk_score,
                     "reasons": [r.message for r in decision.reasons],
                     "tier": decision.tier},
        )

    if decision.tier == "restrict":
        return JSONResponse(
            status_code=429,
            content={"error": "restricted", "risk_score": decision.risk_score,
                     "reasons": [r.message for r in decision.reasons],
                     "action": decision.action,
                     "cooldown_seconds": 60,
                     "tier": decision.tier},
        )

    if decision.tier == "step_up":
        # Generate a fresh OTP for this challenge
        otp_code = f"{secrets.randbelow(1000000):06d}"
        challenge_id = secrets.token_hex(8)
        store = get_store()
        await store.store_otp(challenge_id, otp_code, ttl_seconds=120)
        return JSONResponse(
            status_code=401,
            content={"error": "step_up_required", "risk_score": decision.risk_score,
                     "reasons": [r.message for r in decision.reasons],
                     "challenge": {"method": "otp", "challenge_id": challenge_id,
                                   "demo_otp": otp_code, "ttl_seconds": 120}},
        )

    # tier == allow -> actually forward to the origin service.
    # `service` identifies which upstream to route to; in this MVP there's
    # a single origin (demo-service) so we forward the bare path to it.
    try:
        origin_resp = await forward(request, service, path, identity_id)
        return Response(
            content=origin_resp.content,
            status_code=origin_resp.status_code,
            headers={"x-sentinelx-risk-score": str(decision.risk_score),
                     "x-sentinelx-tier": decision.tier,
                     "x-sentinelx-latency-ms": str(elapsed_ms)},
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
    """Direct resource shortcut: allows callers to hit http://localhost:8080/profile
    or /payments/transfer directly while going through full SentinelX security scoring."""
    raw_path = request.url.path.lstrip("/")
    return await gateway_proxy(service="demo-service", path=raw_path, request=request)

