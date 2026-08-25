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


@router.post("/simulate")
async def simulate(req: SimulateRequest):
    """Fires `count` requests of the given scenario straight through the
    real feature-extraction + rule + ML pipeline (not mocked results) so
    the dashboard shows genuine scoring for the demo."""
    store = get_store()
    valid = {"normal", "frequency_spike", "new_admin_endpoint", "impossible_travel", "privilege_escalation"}
    if req.scenario not in valid:
        raise HTTPException(status_code=400, detail=f"scenario must be one of {sorted(valid)}")

    if req.scenario == "frequency_spike":
        await prime_frequency_spike(store, req.identity_id, n=34)

    results = []
    for _ in range(max(1, req.count)):
        ctx = build_scenario(req.identity_id, req.scenario)
        fv = await extract_features(ctx, store)
        decision = await decide(ctx, fv, store)
        await store.record_request(ctx.identity_id, ctx.endpoint, ctx.geo, ctx.device, ctx.timestamp.hour, ctx.timestamp.timestamp())
        await store.set_risk_state(ctx.identity_id, decision.model_dump(mode="json"))
        if decision.tier != "allow":
            alert = decision.model_dump(mode="json")
            alert["service"] = "origin-demo"
            alert["simulated"] = True
            await store.add_alert(alert)
            log_decision(logger, alert)
        results.append(decision.model_dump(mode="json"))

    return {"scenario": req.scenario, "identity_id": req.identity_id, "results": results}
