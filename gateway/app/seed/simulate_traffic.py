"""
Generates request contexts for demo scenarios, driven either by:
  - `python -m app.seed.simulate_traffic` (standalone, hits a running
    gateway over HTTP -- good for a pre-recorded demo reel), or
  - POST /sentinelx/simulate (in-process, used by the dashboard's
    "Simulate" buttons for a live walkthrough).

Scenarios map directly to the pitch script in §11 of the master doc:
"a normal request flows through untouched; a simulated anomalous request
(frequency spike + new endpoint) gets step-up'd or blocked".
"""
from __future__ import annotations
import random
import string
from datetime import datetime, timezone
from app.models import RequestContext

NORMAL_ENDPOINTS = ["profile", "orders"]
NORMAL_GEOS = ["IN-TN", "IN-KA"]
NORMAL_DEVICES = ["chrome-macos", "safari-ios"]


def _rand_ip() -> str:
    return ".".join(str(random.randint(1, 254)) for _ in range(4))


def _session_id(identity_id: str) -> str:
    return f"sess_{identity_id}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"


def build_scenario(identity_id: str, scenario: str) -> RequestContext:
    now = datetime.now(timezone.utc)
    session_id = _session_id(identity_id)

    if scenario == "normal":
        return RequestContext(
            identity_id=identity_id,
            session_id=session_id,
            endpoint=f"/{random.choice(NORMAL_ENDPOINTS)}",
            method="GET",
            ip=_rand_ip(),
            geo=random.choice(NORMAL_GEOS),
            device=random.choice(NORMAL_DEVICES),
            token_age_seconds=random.uniform(300, 2400),
            payload_size=random.randint(150, 700),
            timestamp=now,
        )

    if scenario == "frequency_spike":
        # Fixed geo/device matching prime_frequency_spike's priming records,
        # so this scenario isolates the frequency signal instead of also
        # accidentally tripping the impossible-travel rule.
        return RequestContext(
            identity_id=identity_id,
            session_id=session_id,
            endpoint="/orders",
            method="GET",
            ip=_rand_ip(),
            geo="IN-TN",
            device="chrome-macos",
            token_age_seconds=random.uniform(300, 2400),
            payload_size=random.randint(150, 700),
            timestamp=now,
        )

    if scenario == "new_admin_endpoint":
        return RequestContext(
            identity_id=identity_id,
            session_id=session_id,
            endpoint="/admin/users",
            method="GET",
            ip=_rand_ip(),
            geo=random.choice(NORMAL_GEOS),
            device=random.choice(NORMAL_DEVICES),
            token_age_seconds=random.uniform(300, 2400),
            payload_size=random.randint(150, 700),
            timestamp=now,
        )

    if scenario == "impossible_travel":
        return RequestContext(
            identity_id=identity_id,
            session_id=session_id,
            endpoint="/profile",
            method="GET",
            ip=_rand_ip(),
            geo=random.choice(["RU-MOW", "BR-SP", "NG-LA"]),
            device="linux-firefox",
            token_age_seconds=random.uniform(10, 90),
            payload_size=random.randint(150, 700),
            timestamp=now,
        )

    if scenario == "privilege_escalation":
        # Uses normal local geo/device so it isolates the privilege escalation signal
        # and triggers Step-Up MFA (Risk ~60) rather than impossible travel revocation.
        return RequestContext(
            identity_id=identity_id,
            session_id=session_id,
            endpoint="/payments/transfer",
            method="POST",
            ip=_rand_ip(),
            geo="IN-TN",
            device="chrome-macos",
            token_age_seconds=random.uniform(600, 1800),
            payload_size=random.randint(250, 600),
            timestamp=now,
        )

    raise ValueError(f"Unknown scenario: {scenario}")


async def prime_frequency_spike(store, identity_id: str, ctx_builder=build_scenario, n: int = 25):
    """Fires N rapid requests into the store just before scoring a request,
    so 'request_frequency_per_min' genuinely reflects a burst -- makes the
    frequency_spike scenario score high for a real reason, not a hardcoded one."""
    import time
    now = time.time()
    current_hour = datetime.now(timezone.utc).hour
    for _ in range(n):
        await store.record_request(identity_id, "/orders", "IN-TN", "chrome-macos", current_hour, now)
