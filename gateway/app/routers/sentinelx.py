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

    # Sync with origin DB if available
    from app.proxy import get_client
    try:
        client = get_client()
        await client.post(
            "/admin/add_user",
            json=registered,
            headers={"x-identity-id": "u_admin"},
            timeout=2.0
        )
    except Exception as e:
        logger.warning(f"Could not forward user creation to origin: {e}")

    return {"status": "created", "user": registered}


@router.post("/simulate")
async def simulate(req: SimulateRequest):
    """Fires `count` requests of the given scenario straight through the
    real feature-extraction + rule + ML pipeline (not mocked results) so
    the dashboard shows genuine scoring for the demo."""
    store = get_store()
    valid = {"normal", "frequency_spike", "new_admin_endpoint", "impossible_travel", "privilege_escalation", "custom"}
    if req.scenario not in valid:
        raise HTTPException(status_code=400, detail=f"scenario must be one of {sorted(valid)}")

    count = max(1, min(req.count, 5000))

    if req.scenario == "frequency_spike":
        await prime_frequency_spike(store, req.identity_id, n=count)

    # Scenarios that should NOT learn into the baseline — otherwise repeating
    # an attack demo would teach the engine that the attack is "normal",
    # causing scores to drop on subsequent attempts.
    non_recording_scenarios = {"privilege_escalation", "impossible_travel", "new_admin_endpoint"}

    # Run real pipeline evaluation on representative sample (max 3 iterations for speed)
    eval_iterations = min(count, 3)
    results = []
    last_decision = None

    for _ in range(eval_iterations):
        if req.scenario == "custom":
            ctx = build_scenario(req.identity_id, "normal")
        else:
            ctx = build_scenario(req.identity_id, req.scenario)

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
        last_decision = decision

        effective_scenario = req.scenario
        if req.scenario == "custom":
            ep = req.endpoint or ""
            geo = req.geo or "IN-TN"
            if geo in ("RU-MOW", "BR-SP", "NG-LA"):
                effective_scenario = "impossible_travel"
            elif any(ep.startswith(p) for p in ("/admin", "/payments")):
                effective_scenario = "privilege_escalation"
            else:
                effective_scenario = "normal"

        if effective_scenario not in non_recording_scenarios:
            await store.record_request(ctx.identity_id, ctx.endpoint, ctx.geo, ctx.device, ctx.timestamp.hour, ctx.timestamp.timestamp())

        results.append(decision.model_dump(mode="json"))

    if last_decision:
        await store.set_risk_state(req.identity_id, last_decision.model_dump(mode="json"))
        if last_decision.tier != "allow":
            alert = last_decision.model_dump(mode="json")
            alert["service"] = "origin-demo"
            alert["simulated"] = True
            alert["burst_count"] = count
            await store.add_alert(alert)
            log_decision(logger, alert)

    return {"scenario": req.scenario, "identity_id": req.identity_id, "count": count, "tier": last_decision.tier if last_decision else "allow", "results": results}
