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

    identity_id = request.headers.get("x-identity-id", "anonymous")
    session_id = request.headers.get("x-session-id", f"sess_{identity_id}_default")
    token_age = float(request.headers.get("x-token-age-seconds", "600"))
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
    )

    fv = await extract_features(ctx, store)
    decision = await decide(ctx, fv, store)

    # Record this request into the behavioural baseline regardless of
    # outcome, so future scoring reflects it (§4.3).
    await store.record_request(ctx.identity_id, ctx.endpoint, ctx.geo, ctx.device, ctx.timestamp.hour, ctx.timestamp.timestamp())
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

    if decision.tier != "allow":
        alert = decision.model_dump(mode="json")
        alert["latency_ms"] = elapsed_ms
        alert["service"] = service
        await store.add_alert(alert)
        log_decision(logger, alert)

    if decision.tier == "revoke":
        await store.revoke_session(ctx.session_id)
        return JSONResponse(
            status_code=401,
            content={"error": "session_revoked", "risk_score": decision.risk_score,
                     "reasons": [r.message for r in decision.reasons]},
        )

    if decision.tier == "restrict":
        return JSONResponse(
            status_code=429,
            content={"error": "restricted", "risk_score": decision.risk_score,
                     "reasons": [r.message for r in decision.reasons],
                     "action": decision.action},
        )

    if decision.tier == "step_up":
        return JSONResponse(
            status_code=401,
            content={"error": "step_up_required", "risk_score": decision.risk_score,
                     "reasons": [r.message for r in decision.reasons],
                     "challenge": {"method": "otp", "ttl_seconds": 300}},
        )

    # tier == allow -> actually forward to the origin service.
    # `service` identifies which upstream to route to; in this MVP there's
    # a single origin (demo-service) so we forward the bare path to it.
    try:
        origin_resp = await forward(request, path, identity_id)
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
