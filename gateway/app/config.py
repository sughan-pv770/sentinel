"""
Central configuration. Everything is env-driven so the same image runs
unchanged locally, in docker-compose, or on Kubernetes — only env vars
change per deployment environment.
"""
from pydantic_settings import BaseSettings
from typing import Dict, Optional


class Settings(BaseSettings):
    app_name: str = "SentinelX Gateway"
    environment: str = "development"  # development | staging | production

    # ── State Store ──────────────────────────────────────────────────────────
    # If unset, state_store.py transparently falls back to an in-memory
    # store with the identical interface — so `uvicorn app.main:app` works
    # with zero external services for local development.
    redis_url: Optional[str] = None

    # ── Origin Service ───────────────────────────────────────────────────────
    # The upstream microservice SentinelX is protecting.
    origin_base_url: str = "http://localhost:9000"

    # ── Latency Budget ───────────────────────────────────────────────────────
    # Target p95 gateway overhead (ms). Surfaced on dashboard + Prometheus.
    latency_budget_ms: float = 15.0

    # ── Behavioral Baseline ──────────────────────────────────────────────────
    baseline_window_requests: int = 500

    # ── Authentication — Access Tokens ───────────────────────────────────────
    # Generate a strong secret: python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret_key: str = "sentinelx-dev-secret-key-change-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60  # 1 hour; use refresh tokens for longer sessions

    # ── Authentication — Refresh Tokens ──────────────────────────────────────
    # Separate secret for refresh tokens so access/refresh can be rotated independently.
    jwt_refresh_secret_key: str = "sentinelx-refresh-secret-key-change-in-production"
    jwt_refresh_expire_hours: int = 168  # 7 days

    # ── MFA ───────────────────────────────────────────────────────────────────
    mfa_totp_issuer: str = "SentinelX"
    mfa_otp_ttl_seconds: int = 300           # OTP validity window
    mfa_totp_window: int = 1                 # Allow ±1 TOTP period for clock skew
    mfa_max_attempts: int = 5               # Lockout after N failed MFA attempts
    mfa_device_trust_days: int = 30         # Trusted device token validity
    # AES-256-GCM key for encrypting TOTP secrets at rest in Redis
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    mfa_encryption_key: str = "REPLACE_ME_IN_PRODUCTION_32BYTE_KEY_=="

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_window_seconds: int = 60     # Sliding window duration
    rate_limit_burst_ceiling: int = 500     # Hard burst limit triggering REVOKE
    rate_limit_step_up_threshold: int = 30  # Requests/window triggering STEP_UP
    rate_limit_enabled: bool = True

    # ── ML Engine ─────────────────────────────────────────────────────────────
    ml_inference_timeout_ms: float = 50.0   # SLA: 95th-percentile scoring budget
    ml_circuit_breaker_threshold: int = 5   # Failures before circuit opens
    ml_circuit_breaker_recovery_s: int = 30 # Seconds before attempting HALF_OPEN
    ml_shadow_mode: bool = False            # Score ML but don't use in decision

    # ── SSE ───────────────────────────────────────────────────────────────────
    sse_ping_interval_seconds: int = 30     # Keep-alive ping period

    # ── Observability ─────────────────────────────────────────────────────────
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: Optional[str] = None  # e.g. http://jaeger:4317
    metrics_enabled: bool = True

    class Config:
        env_file = ".env"
        env_prefix = "SENTINELX_"


settings = Settings()


# Default Zero Trust policy. Mutable at runtime via POST /sentinelx/policy.
DEFAULT_POLICY: Dict = {
    "thresholds": {"allow": 30, "step_up": 60, "restrict": 85},
    "hard_triggers": [
        "privilege_escalation_attempt",
        "token_used_after_revocation",
        "impossible_travel",
        "never_seen_admin_endpoint",
        "rate_burst_surge",
    ],
    "step_up": {
        "method": "totp",           # totp | email_otp
        "fallback": "email_otp",    # fallback if primary unavailable
        "ttl_seconds": 300,
    },
    "restrict": {"action": "rate_limit", "limit_per_minute": 5},
    "mfa_risk_tiers": {
        "low": None,                # Risk 0-30: no MFA
        "medium": "email_otp",     # Risk 31-60: email OTP
        "high": "totp",            # Risk 61-85: TOTP authenticator
        "critical": "totp",        # Risk 86-100: TOTP + force session revoke
    },
}

TIER_ACTION = {
    "allow": "Request proxied normally",
    "step_up": "Step-up authentication required (MFA/OTP)",
    "restrict": "Rate-limited / degraded to read-only",
    "revoke": "Session/token revoked, forced re-login",
}
