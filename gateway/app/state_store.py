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
    async def get_recent_decisions(self, identity_id: str, limit: int = 10) -> list: ...
    async def record_decision(self, identity_id: str, decision: dict): ...
    async def add_incident(self, incident: dict): ...
    async def get_incident(self, incident_id: str) -> dict: ...
    async def get_incidents(self, limit: int = 50, severity: str = None) -> list: ...
    async def update_incident(self, incident: dict): ...
    async def get_incidents_by_identity(self, identity_id: str, limit: int = 20) -> list: ...
    async def get_incident_stats(self) -> dict: ...
    async def register_user(self, identity_id: str, name: str, role: str, network_tag: str = None, supervisor_id: str = None) -> dict: ...
    async def list_users(self) -> list: ...


def _default_profile_dict(role: str = "student") -> dict:
    return {
        "endpoints": {},
        "geos": {},
        "devices": {},
        "hours": [],
        "timestamps": deque(maxlen=MAX_HISTORY_PER_IDENTITY),
        "total": 0,
        "role": role,
    }


class InMemoryStore(BaseStore):
    def __init__(self):
        self._profiles: dict[str, dict] = defaultdict(lambda: _default_profile_dict("student"))
        self._users: dict[str, dict] = {}
        self._risk_state: dict[str, dict] = {}
        self._alerts: deque = deque(maxlen=MAX_ALERTS)
        self._revoked: set[str] = set()
        self._policy: dict = json.loads(json.dumps(DEFAULT_POLICY))
        self._decisions: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self._incidents: deque = deque(maxlen=200)
        self._incidents_by_id: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._seed_default_profiles()

    def _seed_default_profiles(self):
        defaults = [
            ("u_admin", "Priya Nair", "admin", "Core", None,
             {"/admin/add_user": 5, "/admin/users": 10, "/users": 8, "/profile": 12},
             {"IN-TN": 20, "IN-KA": 15}, {"chrome-macos": 35}),
            ("u_manager1", "Prof. Smith", "manager", "CS-Dept", "u_admin",
             {"/profile": 10, "/orders": 12, "/admin/users": 5},
             {"IN-TN": 27}, {"chrome-macos": 27}),
            ("u_alex", "Alex Rao", "student", "CS-Dept-Lab1", "u_manager1",
             {"/profile": 25, "/orders": 30},
             {"IN-TN": 50, "IN-KA": 5}, {"chrome-macos": 45, "safari-ios": 10}),
            ("u_mina", "Mina Okafor", "student", "Library", "u_manager1",
             {"/profile": 20, "/orders": 15},
             {"IN-KA": 35}, {"safari-ios": 35}),
            ("svc_billing", "billing-worker", "service", "Internal", None,
             {"/payments/transfer": 50, "/orders": 30},
             {"IN-TN": 80}, {"internal-service": 80}),
        ]
        now = time.time()
        for uid, name, role, tag, sup, endpoints, geos, devices in defaults:
            self._users[uid] = {
                "identity_id": uid, "name": name, "role": role,
                "network_tag": tag, "supervisor_id": sup
            }
            p = self._profiles[uid]
            p["role"] = role
            p["endpoints"] = dict(endpoints)
            p["geos"] = dict(geos)
            p["devices"] = dict(devices)
            p["hours"] = [9, 10, 11, 12, 14, 15, 16]
            p["total"] = sum(endpoints.values())
            for i in range(min(5, p["total"])):
                p["timestamps"].append(now - (3600 * (i + 1)))

    async def list_users(self) -> list:
        return list(self._users.values())

    async def register_user(self, identity_id: str, name: str, role: str, network_tag: str = None, supervisor_id: str = None) -> dict:
        async with self._lock:
            user_data = {
                "identity_id": identity_id,
                "name": name,
                "role": role,
                "network_tag": network_tag,
                "supervisor_id": supervisor_id,
            }
            self._users[identity_id] = user_data
            p = self._profiles[identity_id]
            p["role"] = role
            p["endpoints"]["/profile"] = 1
            p["geos"]["IN-TN"] = 1
            p["devices"]["chrome-macos"] = 1
            p["total"] = max(p["total"], 1)
            return user_data

    async def get_profile(self, identity_id: str) -> dict:
        p = self._profiles[identity_id]
        return {
            "endpoints": dict(p["endpoints"]),
            "geos": dict(p["geos"]),
            "devices": dict(p["devices"]),
            "hours": list(p["hours"]),
            "timestamps": list(p["timestamps"]),
            "total": p["total"],
            "role": p.get("role", self._users.get(identity_id, {}).get("role", "student")),
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

    async def get_recent_decisions(self, identity_id: str, limit: int = 10) -> list:
        decisions = list(self._decisions[identity_id])
        return decisions[:limit]

    async def record_decision(self, identity_id: str, decision: dict):
        self._decisions[identity_id].appendleft(decision)

    async def add_incident(self, incident: dict):
        self._incidents.appendleft(incident)
        self._incidents_by_id[incident["incident_id"]] = incident

    async def get_incident(self, incident_id: str) -> dict:
        return self._incidents_by_id.get(incident_id)

    async def get_incidents(self, limit: int = 50, severity: str = None) -> list:
        incidents = list(self._incidents)[:limit]
        if severity:
            incidents = [i for i in incidents if i.get("severity") == severity]
        return incidents

    async def update_incident(self, incident: dict):
        self._incidents_by_id[incident["incident_id"]] = incident
        # Update in deque as well
        for i, inc in enumerate(self._incidents):
            if inc["incident_id"] == incident["incident_id"]:
                self._incidents[i] = incident
                break

    async def get_incidents_by_identity(self, identity_id: str, limit: int = 20) -> list:
        incidents = [i for i in self._incidents if i.get("identity_id") == identity_id]
        return incidents[:limit]

    async def get_incident_stats(self) -> dict:
        total = len(self._incidents)
        open_count = sum(1 for i in self._incidents if i.get("status") == "OPEN")
        critical = sum(1 for i in self._incidents if i.get("severity") == "CRITICAL")
        high = sum(1 for i in self._incidents if i.get("severity") == "HIGH")
        return {
            "total_incidents": total,
            "open_incidents": open_count,
            "critical_incidents": critical,
            "high_incidents": high
        }


class RedisStore(BaseStore):
    def __init__(self, url: str):
        import redis.asyncio as aioredis
        self.r = aioredis.from_url(url, decode_responses=True)
        self._policy_key = "sentinelx:policy"
        self._max_decisions = 50

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

    async def get_recent_decisions(self, identity_id: str, limit: int = 10) -> list:
        key = f"sentinelx:decisions:{identity_id}"
        raw = await self.r.lrange(key, 0, limit - 1)
        return [json.loads(x) for x in raw]

    async def record_decision(self, identity_id: str, decision: dict):
        key = f"sentinelx:decisions:{identity_id}"
        await self.r.lpush(key, json.dumps(decision))
        await self.r.ltrim(key, 0, self._max_decisions - 1)
        await self.r.expire(key, 60 * 60 * 24)  # 24 hour TTL

    async def add_incident(self, incident: dict):
        await self.r.lpush("sentinelx:incidents", json.dumps(incident))
        await self.r.ltrim("sentinelx:incidents", 0, 199)
        await self.r.set(f"sentinelx:incident:{incident['incident_id']}", json.dumps(incident), ex=60*60*24*7)

    async def get_incident(self, incident_id: str) -> dict:
        raw = await self.r.get(f"sentinelx:incident:{incident_id}")
        return json.loads(raw) if raw else None

    async def get_incidents(self, limit: int = 50, severity: str = None) -> list:
        raw = await self.r.lrange("sentinelx:incidents", 0, limit - 1)
        incidents = [json.loads(x) for x in raw]
        if severity:
            incidents = [i for i in incidents if i.get("severity") == severity]
        return incidents

    async def update_incident(self, incident: dict):
        await self.r.set(f"sentinelx:incident:{incident['incident_id']}", json.dumps(incident), ex=60*60*24*7)

    async def get_incidents_by_identity(self, identity_id: str, limit: int = 20) -> list:
        raw = await self.r.lrange("sentinelx:incidents", 0, 199)
        all_incidents = [json.loads(x) for x in raw]
        filtered = [i for i in all_incidents if i.get("identity_id") == identity_id]
        return filtered[:limit]

    async def get_incident_stats(self) -> dict:
        raw = await self.r.lrange("sentinelx:incidents", 0, 199)
        incidents = [json.loads(x) for x in raw]
        total = len(incidents)
        open_count = sum(1 for i in incidents if i.get("status") == "OPEN")
        critical = sum(1 for i in incidents if i.get("severity") == "CRITICAL")
        high = sum(1 for i in incidents if i.get("severity") == "HIGH")
        return {
            "total_incidents": total,
            "open_incidents": open_count,
            "critical_incidents": critical,
            "high_incidents": high
        }


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
