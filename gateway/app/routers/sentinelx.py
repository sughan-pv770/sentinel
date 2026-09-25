"""
Control-plane API (§6 of the master doc):
  GET  /sentinelx/risk/{identity_id}
  POST /sentinelx/policy
  GET  /sentinelx/policy
  POST /sentinelx/revoke/{session_id}
  GET  /sentinelx/alerts
  POST /sentinelx/simulate   (extra: drives the dashboard demo buttons)
  GET  /sentinelx/stats      (extra: powers the dashboard header)
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from app.models import PolicyUpdate, SimulateRequest
from app.state_store import get_store
from app.features import extract_features
from app.decision import decide
from app.seed.simulate_traffic import build_scenario, prime_frequency_spike
from app.utils.logger import get_logger, log_decision
from app.config import settings

router = APIRouter(prefix="/sentinelx", tags=["sentinelx"])
logger = get_logger("sentinelx.control")


@router.get("/risk/{identity_id}")
async def get_risk(identity_id: str):
    store = get_store()
    state = await store.get_risk_state(identity_id)
    profile = await store.get_profile(identity_id)
    return {"identity_id": identity_id, "risk_state": state, "total_requests_seen": profile.get("total", 0)}


@router.get("/policy")
async def get_policy():
    store = get_store()
    return await store.get_policy()


@router.post("/policy")
async def update_policy(update: PolicyUpdate):
    store = get_store()
    policy = await store.get_policy()
    data = update.model_dump(exclude_none=True)
    for k, v in data.items():
        if isinstance(policy.get(k), dict) and isinstance(v, dict):
            policy[k].update(v)
        else:
            policy[k] = v
    await store.set_policy(policy)
    return policy


@router.post("/revoke/{session_id}")
async def revoke(session_id: str):
    store = get_store()
    await store.revoke_session(session_id)
    return {"session_id": session_id, "revoked": True}


@router.get("/alerts")
async def get_alerts(limit: int = 50):
    store = get_store()
    return await store.get_alerts(limit)


@router.get("/stats")
async def get_stats():
    store = get_store()
    stats = await store.stats()
    stats["latency_budget_ms"] = settings.latency_budget_ms
    stats["origin_base_url"] = settings.origin_base_url
    return stats


@router.get("/users")
async def get_users():
    store = get_store()
    users = await store.list_users()
    # If store has empty users list, try origin fallback or return defaults
    if not users:
        from app.proxy import get_client
        try:
            client = get_client()
            res = await client.get("/users", headers={"x-identity-id": "u_admin"}, timeout=2.0)
            if res.status_code == 200:
                data = res.json()
                for u in data.get("users", []):
                    await store.register_user(
                        identity_id=u["identity_id"],
                        name=u["name"],
                        role=u["role"],
                        network_tag=u.get("network_tag"),
                        supervisor_id=u.get("supervisor_id"),
                    )
                users = await store.list_users()
        except Exception:
            pass
    return {"users": users}


@router.post("/users")
async def add_user_endpoint(user_data: dict):
    """
    PHASE 3 — Single Creation Path Enforcement:
    This API endpoint MUST remain functional; Orbit calls it every time a user is
    created through signup or Admin Add User. However, the gateway's own UI (Users tab)
    intentionally has NO Add User form — users can only be created through Orbit.
    Do NOT add a UI form here. The read-only Users view in dashboard.html enforces this.
    """
    identity_id = user_data.get("identity_id", "").strip()
    name = user_data.get("name", "").strip()
    role = user_data.get("role", "student")
    network_tag = user_data.get("network_tag")
    supervisor_id = user_data.get("supervisor_id")

    if not identity_id or not name:
        raise HTTPException(status_code=400, detail="identity_id and name are required")

    store = get_store()
    registered = await store.register_user(
        identity_id=identity_id,
        name=name,
        role=role,
        network_tag=network_tag,
        supervisor_id=supervisor_id
    )

    return {"status": "created", "user": registered}


@router.post("/simulate")
async def simulate(req: SimulateRequest):
    """Fires `count` requests of the given scenario straight through the
    real feature-extraction + rule + ML pipeline (not mocked results) so
    the dashboard shows genuine scoring for the demo."""
    store = get_store()
    
    if req.nonce:
        if await store.has_nonce(req.identity_id, req.nonce):
            raise HTTPException(status_code=401, detail="replay_detected")
        await store.store_nonce(req.identity_id, req.nonce)
        
    valid = {"normal", "frequency_spike", "new_admin_endpoint", "impossible_travel", "privilege_escalation", "custom"}
    if req.scenario not in valid:
        raise HTTPException(status_code=400, detail=f"scenario must be one of {sorted(valid)}")

    if req.scenario == "frequency_spike":
        await prime_frequency_spike(store, req.identity_id, n=34)

    # Scenarios that should NOT learn into the baseline — otherwise repeating
    # an attack demo would teach the engine that the attack is "normal",
    # causing scores to drop on subsequent attempts.
    non_recording_scenarios = {"privilege_escalation", "impossible_travel", "new_admin_endpoint"}

    results = []
    for _ in range(max(1, req.count)):
        if req.scenario == "custom":
            ctx = build_scenario(req.identity_id, "normal")
        else:
            ctx = build_scenario(req.identity_id, req.scenario)
        
        ctx.service = "orbit"

        if req.method:
            ctx.method = req.method
        if req.endpoint:
            ctx.endpoint = req.endpoint
        if req.geo:
            ctx.geo = req.geo
        if req.device:
            ctx.device = req.device
        if req.payload_size:
            ctx.payload_size = req.payload_size
        if req.token_age_seconds:
            ctx.token_age_seconds = req.token_age_seconds
            
        fv = await extract_features(ctx, store)
        decision = await decide(ctx, fv, store)

        # Only record benign scenarios into the baseline so attack demos
        # stay reproducible across repeated clicks.
        effective_scenario = req.scenario
        if req.scenario == "custom":
            # For custom, decide based on overrides
            ep = req.endpoint or ""
            geo = req.geo or "IN-TN"
            if geo in ("RU-MOW", "BR-SP", "NG-LA"):
                effective_scenario = "impossible_travel"
            elif any(ep.startswith(p) for p in ("/admin", "/payments")):
                effective_scenario = "privilege_escalation"
            else:
                effective_scenario = "normal"

        if effective_scenario not in non_recording_scenarios:
            await store.record_request(ctx.identity_id, ctx.endpoint, ctx.geo, ctx.device, ctx.timestamp.hour, ctx.timestamp.timestamp(), ctx.payload_size)

        await store.set_risk_state(ctx.identity_id, decision.model_dump(mode="json"))
        if decision.tier != "allow":
            alert = decision.model_dump(mode="json")
            alert["service"] = "origin-demo"
            alert["simulated"] = True
            await store.add_alert(alert)
            log_decision(logger, alert)
        results.append(decision.model_dump(mode="json"))

    return {"scenario": req.scenario, "identity_id": req.identity_id, "results": results}


@router.post("/verify_otp")
async def verify_otp(payload: dict):
    """
    Verify a one-time password issued during a STEP-UP challenge.
    A code is invalidated on first successful use (one-time use).
    Returns: {"result": "ok" | "expired" | "wrong" | "used"}
    """
    challenge_id = payload.get("challenge_id", "")
    code = payload.get("code", "")
    if not challenge_id or not code:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="challenge_id and code are required")

    store = get_store()
    result = await store.verify_otp(challenge_id, str(code))
    status_code = 200 if result == "ok" else 401
    return {"result": result, "challenge_id": challenge_id}


@router.get("/services")
async def list_registered_services():
    """List all services registered in services.json — proof of templatization."""
    from app.service_registry import list_services
    return {"services": list_services()}


# ════════════════════════════════════════════════════════════════
# UNLOCK / RECOVERY ENDPOINTS (Tiered Recovery System)
# ════════════════════════════════════════════════════════════════

@router.get("/unlock")
async def get_locked_accounts():
    """Return all currently identity-revoked accounts."""
    store = get_store()
    revoked_ids = await store.get_revoked_identities()
    users = await store.list_users()
    user_map = {u["identity_id"]: u for u in users}

    locked = []
    for rid in revoked_ids:
        user_info = user_map.get(rid, {"identity_id": rid, "name": rid, "role": "unknown"})
        risk_state = await store.get_risk_state(rid)
        locked.append({
            "identity_id": rid,
            "name": user_info.get("name", rid),
            "role": user_info.get("role", "unknown"),
            "risk_score": risk_state.get("risk_score", 0),
            "tier": "revoke",
            "reasons": risk_state.get("reasons", []),
        })
    return {"locked_accounts": locked}


@router.post("/unlock/request")
async def request_unlock_code(payload: dict):
    """Generate an admin-only Unlock OTP for a revoked identity.
    Called by Orbit's admin panel — the OTP is shown only to the admin."""
    import secrets

    identity_id = payload.get("identity_id", "").strip()
    admin_id = payload.get("admin_id", "unknown")
    if not identity_id:
        raise HTTPException(status_code=400, detail="identity_id is required")

    store = get_store()
    if not await store.is_identity_revoked(identity_id):
        raise HTTPException(status_code=404, detail="Identity is not currently revoked")

    otp_code = f"{secrets.randbelow(1000000):06d}"
    challenge_id = f"unlock_{identity_id}"
    await store.store_otp(challenge_id, otp_code, ttl_seconds=300)

    # Audit: log the unlock request
    import time
    await store.add_alert({
        "type": "unlock_request",
        "identity_id": identity_id,
        "admin_id": admin_id,
        "timestamp": time.time(),
        "message": f"Admin '{admin_id}' generated unlock code for revoked identity '{identity_id}'",
    })
    logger.info(f"UNLOCK REQUEST: admin={admin_id} identity={identity_id}")

    return {
        "identity_id": identity_id,
        "challenge_id": challenge_id,
        "unlock_code": otp_code,
        "ttl_seconds": 300,
    }


@router.post("/unlock/verify")
async def verify_unlock_code(payload: dict):
    """Verify an unlock OTP submitted by a locked-out member.
    On success, lifts the identity-level revocation so they can log in fresh."""
    identity_id = payload.get("identity_id", "").strip()
    code = payload.get("code", "").strip()
    if not identity_id or not code:
        raise HTTPException(status_code=400, detail="identity_id and code are required")

    store = get_store()
    if not await store.is_identity_revoked(identity_id):
        return {"result": "not_revoked", "identity_id": identity_id}

    challenge_id = f"unlock_{identity_id}"
    result = await store.verify_otp(challenge_id, str(code))

    if result == "ok":
        await store.unlock_identity(identity_id)
        # Audit: log the successful unlock
        import time
        await store.add_alert({
            "type": "unlock_success",
            "identity_id": identity_id,
            "timestamp": time.time(),
            "message": f"Identity '{identity_id}' successfully unlocked via admin OTP",
        })
        logger.info(f"UNLOCK SUCCESS: identity={identity_id}")

    return {"result": result, "identity_id": identity_id}


@router.post("/unlock/direct")
async def direct_unlock(payload: dict):
    """Directly unlock an account from the admin panel, bypassing OTP, and reset score."""
    identity_id = payload.get("identity_id", "").strip()
    admin_id = payload.get("admin_id", "unknown")
    if not identity_id:
        raise HTTPException(status_code=400, detail="identity_id is required")

    store = get_store()
    if not await store.is_identity_revoked(identity_id):
        return {"result": "not_revoked", "identity_id": identity_id}

    await store.unlock_identity(identity_id)
    await store.set_risk_state(identity_id, {"risk_score": 0, "tier": "allow", "reasons": []})
    
    import time
    await store.add_alert({
        "type": "unlock_direct",
        "identity_id": identity_id,
        "admin_id": admin_id,
        "timestamp": time.time(),
        "message": f"Admin '{admin_id}' directly unlocked identity '{identity_id}' and reset risk score.",
    })
    logger.info(f"DIRECT UNLOCK SUCCESS: admin={admin_id} identity={identity_id}")

    return {"result": "ok", "identity_id": identity_id}
@router.post("/unlock/reset_all")
async def reset_all_locks():
    """DEV ONLY: Clear all identity-level revocations for fast demo rehearsal."""
    if settings.environment == "production":
        raise HTTPException(status_code=403, detail="Not available in production")

    store = get_store()
    revoked = await store.get_revoked_identities()
    await store.clear_all_revoked_identities()
    logger.info(f"DEV RESET: cleared {len(revoked)} identity locks")
    return {"cleared": revoked, "count": len(revoked)}
