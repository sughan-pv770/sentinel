"""
Central configuration. Everything is env-driven so the same image runs
unchanged locally, in docker-compose, or on Cloud Run -- only env vars
change per §3 / §5 of the master doc.
"""
from pydantic_settings import BaseSettings
from typing import Dict


class Settings(BaseSettings):
    app_name: str = "SentinelX Gateway"
    environment: str = "development"

    # If unset, state_store.py transparently falls back to an in-memory
    # store with the identical interface -- so `uvicorn app.main:app` works
    # with zero external services for a laptop demo.
    redis_url: str | None = None

    # Origin service SentinelX is protecting. In docker-compose this is the
    # `demo-service` container; locally it's localhost:9000.
    origin_base_url: str = "http://localhost:9000"

    # Latency budget target mentioned in §4.1 of the master doc (informational,
    # surfaced on the dashboard).
    latency_budget_ms: float = 15.0

    # Rolling baseline window
    baseline_window_requests: int = 500

    class Config:
        env_file = ".env"
        env_prefix = "SENTINELX_"


settings = Settings()

# Default Zero Trust policy (§7 of the master doc). Mutable at runtime via
# POST /sentinelx/policy -- kept as a module-level dict so both the risk
# engine and the dashboard read the live, current values.
DEFAULT_POLICY: Dict = {
    "thresholds": {"allow": 30, "step_up": 60, "restrict": 85},
    "hard_triggers": [
        "privilege_escalation_attempt",
        "token_used_after_revocation",
        "impossible_travel",
        "never_seen_admin_endpoint",
    ],
    "step_up": {"method": "otp", "ttl_seconds": 300},
    "restrict": {"action": "rate_limit", "limit_per_minute": 5},
}

TIER_ACTION = {
    "allow": "Request proxied normally",
    "step_up": "Step-up authentication required (MFA/OTP)",
    "restrict": "Rate-limited / degraded to read-only",
    "revoke": "Session/token revoked, forced re-login",
}
