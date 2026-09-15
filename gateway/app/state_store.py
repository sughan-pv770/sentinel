"""
Behavioural baseline + risk state storage.

Two implementations share the exact same async interface:
  - RedisStore    — real Redis, used when SENTINELX_REDIS_URL is set
                    (docker-compose / Kubernetes wires this up automatically).
  - InMemoryStore — a plain-Python fallback so the gateway is fully
                    runnable with `uvicorn app.main:app` and zero
                    external services, for local development.

Production additions vs. prototype:
  - MFA challenge + TOTP enrollment storage (TTL-bound)
  - JTI (JWT ID) blacklist for individual token revocation
  - revoke_all_user_sessions() for ML-triggered global session kill
  - Sliding-window rate limit check (atomic Redis pipeline)
  - Session revocation audit log
"""
from __future__ import annotations
import json
import time
import asyncio
import hashlib
from collections import deque, defaultdict
from typing import Any, Optional, List

from app.config import settings, DEFAULT_POLICY

MAX_ALERTS = 200
MAX_HISTORY_PER_IDENTITY = 500
MAX_REVOCATION_AUDIT = 500


# ── Abstract base ──────────────────────────────────────────────────────────────

class BaseStore:
    # Behavioural profile
    async def get_profile(self, identity_id: str) -> dict: ...
    async def record_request(self, identity_id: str, endpoint: str, geo: str, device: str, hour: int, ts: float): ...

    # Risk state
    async def get_risk_state(self, identity_id: str) -> dict: ...
    async def set_risk_state(self, identity_id: str, state: dict): ...

    # Alerts & incidents
    async def add_alert(self, alert: dict): ...
    async def get_alerts(self, limit: int = 50) -> list: ...
    async def add_incident(self, incident: dict): ...
    async def get_incident(self, incident_id: str) -> dict: ...
    async def get_incidents(self, limit: int = 50, severity: str = None) -> list: ...
    async def update_incident(self, incident: dict): ...
    async def get_incidents_by_identity(self, identity_id: str, limit: int = 20) -> list: ...
    async def get_incident_stats(self) -> dict: ...

    # Session management
    async def revoke_session(self, session_id: str): ...
    async def is_revoked(self, session_id: str) -> bool: ...
    async def revoke_jti(self, jti: str, ttl_seconds: int = 86400): ...
    async def is_jti_revoked(self, jti: str) -> bool: ...
    async def revoke_all_user_sessions(self, identity_id: str) -> List[str]: ...
    async def register_active_session(self, identity_id: str, session_id: str, jti: str): ...
    async def get_active_sessions(self, identity_id: str) -> List[dict]: ...
    async def add_revocation_audit(self, event: dict): ...
    async def get_revocation_audit(self, limit: int = 50) -> list: ...

    # Policy
    async def get_policy(self) -> dict: ...
    async def set_policy(self, policy: dict): ...

    # Stats & decisions
    async def stats(self) -> dict: ...
    async def get_recent_decisions(self, identity_id: str, limit: int = 10) -> list: ...
    async def record_decision(self, identity_id: str, decision: dict): ...

    # User registry
    async def register_user(self, identity_id: str, name: str, role: str, network_tag: str = None, supervisor_id: str = None) -> dict: ...
    async def list_users(self) -> list: ...

    # MFA
    async def store_mfa_challenge(self, session_id: str, challenge: dict, ttl_seconds: int = 300): ...
    async def get_mfa_challenge(self, session_id: str) -> Optional[dict]: ...
    async def delete_mfa_challenge(self, session_id: str): ...
    async def store_totp_secret(self, identity_id: str, encrypted_secret: str): ...
    async def get_totp_secret(self, identity_id: str) -> Optional[str]: ...
    async def store_mfa_enrollment(self, identity_id: str, enrollment: dict): ...
    async def get_mfa_enrollment(self, identity_id: str) -> Optional[dict]: ...
    async def store_device_trust(self, token_id: str, trust_data: dict, ttl_seconds: int): ...
    async def get_device_trust(self, token_id: str) -> Optional[dict]: ...
    async def revoke_device_trust(self, token_id: str): ...
    async def mark_session_mfa_complete(self, session_id: str, method: str): ...
    async def is_session_mfa_complete(self, session_id: str) -> bool: ...

    # Rate limiting (atomic sliding window)
    async def rate_limit_check(self, key: str, window_seconds: int, limit: int) -> dict: ...


# ── Helpers ────────────────────────────────────────────────────────────────────

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


# ── InMemoryStore ──────────────────────────────────────────────────────────────

class InMemoryStore(BaseStore):
    def __init__(self):
        self._profiles: dict[str, dict] = defaultdict(lambda: _default_profile_dict("student"))
        self._users: dict[str, dict] = {}
        self._risk_state: dict[str, dict] = {}
        self._alerts: deque = deque(maxlen=MAX_ALERTS)
        self._revoked_sessions: set[str] = set()
        self._revoked_jtis: dict[str, float] = {}  # jti -> expiry ts
        self._active_sessions: dict[str, list] = defaultdict(list)  # identity_id -> [session_info]
        self._revocation_audit: deque = deque(maxlen=MAX_REVOCATION_AUDIT)
        self._policy: dict = json.loads(json.dumps(DEFAULT_POLICY))
        self._decisions: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self._incidents: deque = deque(maxlen=200)
        self._incidents_by_id: dict[str, dict] = {}
        self._mfa_challenges: dict[str, dict] = {}  # session_id -> challenge
        self._mfa_challenges_expiry: dict[str, float] = {}
        self._mfa_enrollments: dict[str, dict] = {}  # identity_id -> enrollment
        self._device_trusts: dict[str, dict] = {}   # token_id -> trust_data
        self._device_trusts_expiry: dict[str, float] = {}
        self._mfa_complete_sessions: set[str] = set()
        self._rate_counters: dict[str, list] = defaultdict(list)  # key -> [timestamps]
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

    # ── User registry ──────────────────────────────────────────────────────────

    async def list_users(self) -> list:
        return list(self._users.values())

    async def register_user(self, identity_id: str, name: str, role: str, network_tag: str = None, supervisor_id: str = None) -> dict:
        async with self._lock:
            user_data = {
                "identity_id": identity_id, "name": name, "role": role,
                "network_tag": network_tag, "supervisor_id": supervisor_id,
            }
            self._users[identity_id] = user_data
            p = self._profiles[identity_id]
            p["role"] = role
            p["endpoints"].setdefault("/profile", 1)
            p["geos"].setdefault("IN-TN", 1)
            p["devices"].setdefault("chrome-macos", 1)
            p["total"] = max(p["total"], 1)
            return user_data

    # ── Behavioural profile ────────────────────────────────────────────────────

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

    # ── Risk state ─────────────────────────────────────────────────────────────

    async def get_risk_state(self, identity_id: str) -> dict:
        return self._risk_state.get(identity_id, {"risk_score": 0, "tier": "allow", "reasons": []})

    async def set_risk_state(self, identity_id: str, state: dict):
        self._risk_state[identity_id] = state

    # ── Alerts & incidents ─────────────────────────────────────────────────────

    async def add_alert(self, alert: dict):
        self._alerts.appendleft(alert)

    async def get_alerts(self, limit: int = 50) -> list:
        return list(self._alerts)[:limit]

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
        for i, inc in enumerate(self._incidents):
            if inc["incident_id"] == incident["incident_id"]:
                self._incidents[i] = incident
                break

    async def get_incidents_by_identity(self, identity_id: str, limit: int = 20) -> list:
        return [i for i in self._incidents if i.get("identity_id") == identity_id][:limit]

    async def get_incident_stats(self) -> dict:
        total = len(self._incidents)
        return {
            "total_incidents": total,
            "open_incidents": sum(1 for i in self._incidents if i.get("status") == "OPEN"),
            "critical_incidents": sum(1 for i in self._incidents if i.get("severity") == "CRITICAL"),
            "high_incidents": sum(1 for i in self._incidents if i.get("severity") == "HIGH"),
        }

    # ── Session management ─────────────────────────────────────────────────────

    async def revoke_session(self, session_id: str):
        self._revoked_sessions.add(session_id)

    async def is_revoked(self, session_id: str) -> bool:
        return session_id in self._revoked_sessions

    async def revoke_jti(self, jti: str, ttl_seconds: int = 86400):
        self._revoked_jtis[jti] = time.time() + ttl_seconds

    async def is_jti_revoked(self, jti: str) -> bool:
        expiry = self._revoked_jtis.get(jti)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._revoked_jtis[jti]
            return False
        return True

    async def register_active_session(self, identity_id: str, session_id: str, jti: str):
        async with self._lock:
            sessions = self._active_sessions[identity_id]
            sessions.append({"session_id": session_id, "jti": jti, "created_at": time.time()})
            # Cap at 20 concurrent sessions
            if len(sessions) > 20:
                self._active_sessions[identity_id] = sessions[-20:]

    async def get_active_sessions(self, identity_id: str) -> List[dict]:
        return list(self._active_sessions.get(identity_id, []))

    async def revoke_all_user_sessions(self, identity_id: str) -> List[str]:
        """Revoke all tracked sessions and JTIs for an identity. Returns revoked session IDs."""
        async with self._lock:
            sessions = self._active_sessions.pop(identity_id, [])
            revoked_ids = []
            for s in sessions:
                sid = s.get("session_id")
                jti = s.get("jti")
                if sid:
                    self._revoked_sessions.add(sid)
                    revoked_ids.append(sid)
                if jti:
                    self._revoked_jtis[jti] = time.time() + 86400
            return revoked_ids

    async def add_revocation_audit(self, event: dict):
        self._revocation_audit.appendleft(event)

    async def get_revocation_audit(self, limit: int = 50) -> list:
        return list(self._revocation_audit)[:limit]

    # ── Policy ─────────────────────────────────────────────────────────────────

    async def get_policy(self) -> dict:
        return json.loads(json.dumps(self._policy))

    async def set_policy(self, policy: dict):
        self._policy = policy

    # ── Stats & decisions ──────────────────────────────────────────────────────

    async def stats(self) -> dict:
        return {
            "backend": "in-memory",
            "identities_tracked": len(self._profiles),
            "alerts_buffered": len(self._alerts),
            "revoked_sessions": len(self._revoked_sessions),
            "revoked_jtis": len(self._revoked_jtis),
            "active_sessions_tracked": sum(len(v) for v in self._active_sessions.values()),
            "mfa_challenges_active": len(self._mfa_challenges),
            "mfa_enrollments": len(self._mfa_enrollments),
        }

    async def get_recent_decisions(self, identity_id: str, limit: int = 10) -> list:
        return list(self._decisions[identity_id])[:limit]

    async def record_decision(self, identity_id: str, decision: dict):
        self._decisions[identity_id].appendleft(decision)

    # ── MFA ────────────────────────────────────────────────────────────────────

    async def store_mfa_challenge(self, session_id: str, challenge: dict, ttl_seconds: int = 300):
        self._mfa_challenges[session_id] = challenge
        self._mfa_challenges_expiry[session_id] = time.time() + ttl_seconds

    async def get_mfa_challenge(self, session_id: str) -> Optional[dict]:
        expiry = self._mfa_challenges_expiry.get(session_id)
        if expiry and time.time() > expiry:
            self._mfa_challenges.pop(session_id, None)
            self._mfa_challenges_expiry.pop(session_id, None)
            return None
        return self._mfa_challenges.get(session_id)

    async def delete_mfa_challenge(self, session_id: str):
        self._mfa_challenges.pop(session_id, None)
        self._mfa_challenges_expiry.pop(session_id, None)

    async def store_totp_secret(self, identity_id: str, encrypted_secret: str):
        enrollment = self._mfa_enrollments.get(identity_id, {})
        enrollment["encrypted_secret"] = encrypted_secret
        self._mfa_enrollments[identity_id] = enrollment

    async def get_totp_secret(self, identity_id: str) -> Optional[str]:
        return self._mfa_enrollments.get(identity_id, {}).get("encrypted_secret")

    async def store_mfa_enrollment(self, identity_id: str, enrollment: dict):
        self._mfa_enrollments[identity_id] = enrollment

    async def get_mfa_enrollment(self, identity_id: str) -> Optional[dict]:
        return self._mfa_enrollments.get(identity_id)

    async def store_device_trust(self, token_id: str, trust_data: dict, ttl_seconds: int):
        self._device_trusts[token_id] = trust_data
        self._device_trusts_expiry[token_id] = time.time() + ttl_seconds

    async def get_device_trust(self, token_id: str) -> Optional[dict]:
        expiry = self._device_trusts_expiry.get(token_id)
        if expiry and time.time() > expiry:
            self._device_trusts.pop(token_id, None)
            self._device_trusts_expiry.pop(token_id, None)
            return None
        return self._device_trusts.get(token_id)

    async def revoke_device_trust(self, token_id: str):
        self._device_trusts.pop(token_id, None)
        self._device_trusts_expiry.pop(token_id, None)

    async def mark_session_mfa_complete(self, session_id: str, method: str):
        self._mfa_complete_sessions.add(session_id)

    async def is_session_mfa_complete(self, session_id: str) -> bool:
        return session_id in self._mfa_complete_sessions

    # ── Rate limiting ──────────────────────────────────────────────────────────

    async def rate_limit_check(self, key: str, window_seconds: int, limit: int) -> dict:
        """Sliding window rate limiter. Returns state dict with exceeded flag."""
        now = time.time()
        window_start = now - window_seconds
        async with self._lock:
            # Prune old timestamps
            self._rate_counters[key] = [
                ts for ts in self._rate_counters[key] if ts > window_start
            ]
            count = len(self._rate_counters[key])
            exceeded = count >= limit
            if not exceeded:
                self._rate_counters[key].append(now)
                count += 1
        return {
            "key": key,
            "count": count,
            "window_start": window_start,
            "limit": limit,
            "burst_remaining": max(0, limit - count),
            "exceeded": exceeded,
        }


# ── RedisStore ─────────────────────────────────────────────────────────────────

class RedisStore(BaseStore):
    def __init__(self, url: str):
        import redis.asyncio as aioredis
        self.r = aioredis.from_url(url, decode_responses=True)
        self._policy_key = "sentinelx:policy"
        self._max_decisions = 50

    def _pkey(self, identity_id: str) -> str:
        return f"sentinelx:profile:{identity_id}"

    # ── User registry ──────────────────────────────────────────────────────────

    async def list_users(self) -> list:
        keys = await self.r.keys("sentinelx:user:*")
        if not keys:
            return []
        values = await self.r.mget(*keys)
        return [json.loads(v) for v in values if v]

    async def register_user(self, identity_id: str, name: str, role: str, network_tag: str = None, supervisor_id: str = None) -> dict:
        user_data = {
            "identity_id": identity_id, "name": name, "role": role,
            "network_tag": network_tag, "supervisor_id": supervisor_id,
        }
        await self.r.set(f"sentinelx:user:{identity_id}", json.dumps(user_data))
        # Init profile
        key = self._pkey(identity_id)
        if not await self.r.exists(key):
            await self.r.set(key, json.dumps({
                "endpoints": {"/profile": 1}, "geos": {"IN-TN": 1},
                "devices": {"chrome-macos": 1}, "hours": [], "timestamps": [], "total": 1, "role": role,
            }), ex=60 * 60 * 24 * 7)
        return user_data

    # ── Behavioural profile ────────────────────────────────────────────────────

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
        p["hours"] = (p["hours"] + [hour])[-MAX_HISTORY_PER_IDENTITY:]
        p["timestamps"] = (p["timestamps"] + [ts])[-MAX_HISTORY_PER_IDENTITY:]
        p["total"] += 1
        await self.r.set(key, json.dumps(p), ex=60 * 60 * 24 * 7)

    # ── Risk state ─────────────────────────────────────────────────────────────

    async def get_risk_state(self, identity_id: str) -> dict:
        raw = await self.r.get(f"sentinelx:risk:{identity_id}")
        return json.loads(raw) if raw else {"risk_score": 0, "tier": "allow", "reasons": []}

    async def set_risk_state(self, identity_id: str, state: dict):
        await self.r.set(f"sentinelx:risk:{identity_id}", json.dumps(state), ex=3600)

    # ── Alerts & incidents ─────────────────────────────────────────────────────

    async def add_alert(self, alert: dict):
        await self.r.lpush("sentinelx:alerts", json.dumps(alert))
        await self.r.ltrim("sentinelx:alerts", 0, MAX_ALERTS - 1)

    async def get_alerts(self, limit: int = 50) -> list:
        return [json.loads(x) for x in await self.r.lrange("sentinelx:alerts", 0, limit - 1)]

    async def add_incident(self, incident: dict):
        await self.r.lpush("sentinelx:incidents", json.dumps(incident))
        await self.r.ltrim("sentinelx:incidents", 0, 199)
        await self.r.set(f"sentinelx:incident:{incident['incident_id']}", json.dumps(incident), ex=60*60*24*7)

    async def get_incident(self, incident_id: str) -> dict:
        raw = await self.r.get(f"sentinelx:incident:{incident_id}")
        return json.loads(raw) if raw else None

    async def get_incidents(self, limit: int = 50, severity: str = None) -> list:
        incidents = [json.loads(x) for x in await self.r.lrange("sentinelx:incidents", 0, limit - 1)]
        if severity:
            incidents = [i for i in incidents if i.get("severity") == severity]
        return incidents

    async def update_incident(self, incident: dict):
        await self.r.set(f"sentinelx:incident:{incident['incident_id']}", json.dumps(incident), ex=60*60*24*7)

    async def get_incidents_by_identity(self, identity_id: str, limit: int = 20) -> list:
        all_inc = [json.loads(x) for x in await self.r.lrange("sentinelx:incidents", 0, 199)]
        return [i for i in all_inc if i.get("identity_id") == identity_id][:limit]

    async def get_incident_stats(self) -> dict:
        incidents = [json.loads(x) for x in await self.r.lrange("sentinelx:incidents", 0, 199)]
        return {
            "total_incidents": len(incidents),
            "open_incidents": sum(1 for i in incidents if i.get("status") == "OPEN"),
            "critical_incidents": sum(1 for i in incidents if i.get("severity") == "CRITICAL"),
            "high_incidents": sum(1 for i in incidents if i.get("severity") == "HIGH"),
        }

    # ── Session management ─────────────────────────────────────────────────────

    async def revoke_session(self, session_id: str):
        await self.r.sadd("sentinelx:revoked", session_id)
        await self.r.expire("sentinelx:revoked", 60 * 60 * 24 * 7)

    async def is_revoked(self, session_id: str) -> bool:
        return bool(await self.r.sismember("sentinelx:revoked", session_id))

    async def revoke_jti(self, jti: str, ttl_seconds: int = 86400):
        await self.r.set(f"sentinelx:jti:revoked:{jti}", "1", ex=ttl_seconds)

    async def is_jti_revoked(self, jti: str) -> bool:
        return bool(await self.r.exists(f"sentinelx:jti:revoked:{jti}"))

    async def register_active_session(self, identity_id: str, session_id: str, jti: str):
        key = f"sentinelx:sessions:{identity_id}"
        session_data = json.dumps({"session_id": session_id, "jti": jti, "created_at": time.time()})
        await self.r.lpush(key, session_data)
        await self.r.ltrim(key, 0, 19)  # Cap at 20 sessions
        await self.r.expire(key, 60 * 60 * 24 * 8)

    async def get_active_sessions(self, identity_id: str) -> List[dict]:
        raw = await self.r.lrange(f"sentinelx:sessions:{identity_id}", 0, -1)
        return [json.loads(x) for x in raw]

    async def revoke_all_user_sessions(self, identity_id: str) -> List[str]:
        sessions = await self.get_active_sessions(identity_id)
        pipe = self.r.pipeline()
        revoked_ids = []
        for s in sessions:
            sid = s.get("session_id")
            jti = s.get("jti")
            if sid:
                pipe.sadd("sentinelx:revoked", sid)
                revoked_ids.append(sid)
            if jti:
                pipe.set(f"sentinelx:jti:revoked:{jti}", "1", ex=86400)
        pipe.delete(f"sentinelx:sessions:{identity_id}")
        await pipe.execute()
        return revoked_ids

    async def add_revocation_audit(self, event: dict):
        await self.r.lpush("sentinelx:revocation_audit", json.dumps(event))
        await self.r.ltrim("sentinelx:revocation_audit", 0, MAX_REVOCATION_AUDIT - 1)

    async def get_revocation_audit(self, limit: int = 50) -> list:
        return [json.loads(x) for x in await self.r.lrange("sentinelx:revocation_audit", 0, limit - 1)]

    # ── Policy ─────────────────────────────────────────────────────────────────

    async def get_policy(self) -> dict:
        raw = await self.r.get(self._policy_key)
        return json.loads(raw) if raw else json.loads(json.dumps(DEFAULT_POLICY))

    async def set_policy(self, policy: dict):
        await self.r.set(self._policy_key, json.dumps(policy))

    # ── Stats & decisions ──────────────────────────────────────────────────────

    async def stats(self) -> dict:
        n_revoked = await self.r.scard("sentinelx:revoked")
        n_alerts = await self.r.llen("sentinelx:alerts")
        return {
            "backend": "redis",
            "revoked_sessions": n_revoked,
            "alerts_buffered": n_alerts,
        }

    async def get_recent_decisions(self, identity_id: str, limit: int = 10) -> list:
        key = f"sentinelx:decisions:{identity_id}"
        return [json.loads(x) for x in await self.r.lrange(key, 0, limit - 1)]

    async def record_decision(self, identity_id: str, decision: dict):
        key = f"sentinelx:decisions:{identity_id}"
        await self.r.lpush(key, json.dumps(decision))
        await self.r.ltrim(key, 0, self._max_decisions - 1)
        await self.r.expire(key, 60 * 60 * 24)

    # ── MFA ────────────────────────────────────────────────────────────────────

    async def store_mfa_challenge(self, session_id: str, challenge: dict, ttl_seconds: int = 300):
        await self.r.set(f"sentinelx:mfa:challenge:{session_id}", json.dumps(challenge), ex=ttl_seconds)

    async def get_mfa_challenge(self, session_id: str) -> Optional[dict]:
        raw = await self.r.get(f"sentinelx:mfa:challenge:{session_id}")
        return json.loads(raw) if raw else None

    async def delete_mfa_challenge(self, session_id: str):
        await self.r.delete(f"sentinelx:mfa:challenge:{session_id}")

    async def store_totp_secret(self, identity_id: str, encrypted_secret: str):
        key = f"sentinelx:mfa:enrollment:{identity_id}"
        raw = await self.r.get(key)
        enrollment = json.loads(raw) if raw else {}
        enrollment["encrypted_secret"] = encrypted_secret
        await self.r.set(key, json.dumps(enrollment))

    async def get_totp_secret(self, identity_id: str) -> Optional[str]:
        raw = await self.r.get(f"sentinelx:mfa:enrollment:{identity_id}")
        return json.loads(raw).get("encrypted_secret") if raw else None

    async def store_mfa_enrollment(self, identity_id: str, enrollment: dict):
        await self.r.set(f"sentinelx:mfa:enrollment:{identity_id}", json.dumps(enrollment))

    async def get_mfa_enrollment(self, identity_id: str) -> Optional[dict]:
        raw = await self.r.get(f"sentinelx:mfa:enrollment:{identity_id}")
        return json.loads(raw) if raw else None

    async def store_device_trust(self, token_id: str, trust_data: dict, ttl_seconds: int):
        await self.r.set(f"sentinelx:device_trust:{token_id}", json.dumps(trust_data), ex=ttl_seconds)

    async def get_device_trust(self, token_id: str) -> Optional[dict]:
        raw = await self.r.get(f"sentinelx:device_trust:{token_id}")
        return json.loads(raw) if raw else None

    async def revoke_device_trust(self, token_id: str):
        await self.r.delete(f"sentinelx:device_trust:{token_id}")

    async def mark_session_mfa_complete(self, session_id: str, method: str):
        await self.r.set(f"sentinelx:mfa:complete:{session_id}", method, ex=3600)

    async def is_session_mfa_complete(self, session_id: str) -> bool:
        return bool(await self.r.exists(f"sentinelx:mfa:complete:{session_id}"))

    # ── Rate limiting (atomic Redis INCR sliding window) ───────────────────────

    async def rate_limit_check(self, key: str, window_seconds: int, limit: int) -> dict:
        """Atomic sliding window using Redis sorted set (ZRANGEBYSCORE + ZADD + ZREMRANGEBYSCORE)."""
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"sentinelx:ratelimit:{key}"

        pipe = self.r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {f"{now}:{id(pipe)}": now})
        pipe.expire(redis_key, window_seconds + 1)
        results = await pipe.execute()

        count_before_add = results[1]
        count = count_before_add + 1
        exceeded = count_before_add >= limit

        if exceeded:
            # Remove the element we just added (don't count exceeded requests)
            await self.r.zremrangebyscore(redis_key, now - 0.001, now + 0.001)

        return {
            "key": key,
            "count": count_before_add,
            "window_start": window_start,
            "limit": limit,
            "burst_remaining": max(0, limit - count_before_add),
            "exceeded": exceeded,
        }


# ── Singleton factory ──────────────────────────────────────────────────────────

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
