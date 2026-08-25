"""
Behavioural baseline + risk state storage (§4.3 of the master doc).

Two implementations share the exact same async interface:
  - RedisStore     -- real Redis, used when SENTINELX_REDIS_URL is set
                       (docker-compose wires this up automatically).
  - InMemoryStore   -- a plain-Python fallback so the gateway is fully
                       runnable with `uvicorn app.main:app` and zero
                       external services, for a quick laptop demo.

Everything is stored as compact aggregates (counts, EWMA, small rolling
deques) rather than raw request logs, per the "stays low-latency" design
note in the master doc.
"""
from __future__ import annotations
import json
import time
import asyncio
from collections import deque, defaultdict
from typing import Any, Optional

from app.config import settings, DEFAULT_POLICY

MAX_ALERTS = 200
MAX_HISTORY_PER_IDENTITY = 500


class BaseStore:
    async def get_profile(self, identity_id: str) -> dict: ...
    async def record_request(self, identity_id: str, endpoint: str, geo: str, device: str, hour: int, ts: float): ...
    async def get_risk_state(self, identity_id: str) -> dict: ...
    async def set_risk_state(self, identity_id: str, state: dict): ...
    async def add_alert(self, alert: dict): ...
    async def get_alerts(self, limit: int = 50) -> list: ...
    async def revoke_session(self, session_id: str): ...
    async def is_revoked(self, session_id: str) -> bool: ...
    async def get_policy(self) -> dict: ...
    async def set_policy(self, policy: dict): ...
    async def stats(self) -> dict: ...


class InMemoryStore(BaseStore):
    def __init__(self):
        self._profiles: dict[str, dict] = defaultdict(
            lambda: {"endpoints": {}, "geos": {}, "devices": {}, "hours": [], "timestamps": deque(maxlen=MAX_HISTORY_PER_IDENTITY), "total": 0}
        )
        self._risk_state: dict[str, dict] = {}
        self._alerts: deque = deque(maxlen=MAX_ALERTS)
        self._revoked: set[str] = set()
        self._policy: dict = json.loads(json.dumps(DEFAULT_POLICY))
        self._lock = asyncio.Lock()

    async def get_profile(self, identity_id: str) -> dict:
        p = self._profiles[identity_id]
        return {
            "endpoints": dict(p["endpoints"]),
            "geos": dict(p["geos"]),
            "devices": dict(p["devices"]),
            "hours": list(p["hours"]),
            "timestamps": list(p["timestamps"]),
            "total": p["total"],
        }

    async def record_request(self, identity_id: str, endpoint: str, geo: str, device: str, hour: int, ts: float):
        async with self._lock:
            p = self._profiles[identity_id]
            p["endpoints"][endpoint] = p["endpoints"].get(endpoint, 0) + 1
            p["geos"][geo] = p["geos"].get(geo, 0) + 1
            p["devices"][device] = p["devices"].get(device, 0) + 1
            p["hours"].append(hour)
            if len(p["hours"]) > MAX_HISTORY_PER_IDENTITY:
                p["hours"].pop(0)
            p["timestamps"].append(ts)
            p["total"] += 1

    async def get_risk_state(self, identity_id: str) -> dict:
        return self._risk_state.get(identity_id, {"risk_score": 0, "tier": "allow", "reasons": []})

    async def set_risk_state(self, identity_id: str, state: dict):
        self._risk_state[identity_id] = state

    async def add_alert(self, alert: dict):
        self._alerts.appendleft(alert)

    async def get_alerts(self, limit: int = 50) -> list:
        return list(self._alerts)[:limit]

    async def revoke_session(self, session_id: str):
        self._revoked.add(session_id)

    async def is_revoked(self, session_id: str) -> bool:
        return session_id in self._revoked

    async def get_policy(self) -> dict:
        return json.loads(json.dumps(self._policy))

    async def set_policy(self, policy: dict):
        self._policy = policy

    async def stats(self) -> dict:
        return {
            "backend": "in-memory",
            "identities_tracked": len(self._profiles),
            "alerts_buffered": len(self._alerts),
            "revoked_sessions": len(self._revoked),
        }


class RedisStore(BaseStore):
    def __init__(self, url: str):
        import redis.asyncio as aioredis
        self.r = aioredis.from_url(url, decode_responses=True)
        self._policy_key = "sentinelx:policy"

    def _pkey(self, identity_id: str) -> str:
        return f"sentinelx:profile:{identity_id}"

    async def get_profile(self, identity_id: str) -> dict:
        raw = await self.r.get(self._pkey(identity_id))
        if not raw:
            return {"endpoints": {}, "geos": {}, "devices": {}, "hours": [], "timestamps": [], "total": 0}
        return json.loads(raw)

    async def record_request(self, identity_id: str, endpoint: str, geo: str, device: str, hour: int, ts: float):
        key = self._pkey(identity_id)
        raw = await self.r.get(key)
        p = json.loads(raw) if raw else {"endpoints": {}, "geos": {}, "devices": {}, "hours": [], "timestamps": [], "total": 0}
        p["endpoints"][endpoint] = p["endpoints"].get(endpoint, 0) + 1
        p["geos"][geo] = p["geos"].get(geo, 0) + 1
        p["devices"][device] = p["devices"].get(device, 0) + 1
        p["hours"].append(hour)
        p["hours"] = p["hours"][-MAX_HISTORY_PER_IDENTITY:]
        p["timestamps"].append(ts)
        p["timestamps"] = p["timestamps"][-MAX_HISTORY_PER_IDENTITY:]
        p["total"] += 1
        await self.r.set(key, json.dumps(p), ex=60 * 60 * 24 * 7)

    async def get_risk_state(self, identity_id: str) -> dict:
        raw = await self.r.get(f"sentinelx:risk:{identity_id}")
        return json.loads(raw) if raw else {"risk_score": 0, "tier": "allow", "reasons": []}

    async def set_risk_state(self, identity_id: str, state: dict):
        await self.r.set(f"sentinelx:risk:{identity_id}", json.dumps(state), ex=3600)

    async def add_alert(self, alert: dict):
        await self.r.lpush("sentinelx:alerts", json.dumps(alert))
        await self.r.ltrim("sentinelx:alerts", 0, MAX_ALERTS - 1)

    async def get_alerts(self, limit: int = 50) -> list:
        raw = await self.r.lrange("sentinelx:alerts", 0, limit - 1)
        return [json.loads(x) for x in raw]

    async def revoke_session(self, session_id: str):
        await self.r.sadd("sentinelx:revoked", session_id)

    async def is_revoked(self, session_id: str) -> bool:
        return bool(await self.r.sismember("sentinelx:revoked", session_id))

    async def get_policy(self) -> dict:
        raw = await self.r.get(self._policy_key)
        return json.loads(raw) if raw else json.loads(json.dumps(DEFAULT_POLICY))

    async def set_policy(self, policy: dict):
        await self.r.set(self._policy_key, json.dumps(policy))

    async def stats(self) -> dict:
        n_revoked = await self.r.scard("sentinelx:revoked")
        n_alerts = await self.r.llen("sentinelx:alerts")
        return {"backend": "redis", "revoked_sessions": n_revoked, "alerts_buffered": n_alerts}


_store_instance: Optional[BaseStore] = None


def get_store() -> BaseStore:
    global _store_instance
    if _store_instance is not None:
        return _store_instance
    if settings.redis_url:
        try:
            _store_instance = RedisStore(settings.redis_url)
        except Exception:
            _store_instance = InMemoryStore()
    else:
        _store_instance = InMemoryStore()
    return _store_instance
