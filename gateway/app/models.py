from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


class RequestContext(BaseModel):
    identity_id: str
    session_id: str
    endpoint: str
    method: str
    ip: str
    geo: str
    device: str
    token_age_seconds: float
    payload_size: int
    jti: Optional[str] = None          # JWT ID for individual token revocation
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureVector(BaseModel):
    request_frequency_per_min: float
    endpoint_novelty: float          # 0 = seen before, 1 = never seen
    geo_change: float                # 0/1
    device_change: float             # 0/1
    time_of_day_deviation: float     # hours away from typical hour, normalized
    payload_size_zscore: float
    token_age_seconds: float


class Reason(BaseModel):
    code: str
    message: str


class RiskDecision(BaseModel):
    identity_id: str
    session_id: str
    endpoint: str
    risk_score: float
    tier: str
    action: str
    reasons: List[Reason]
    rule_triggered: bool
    ml_score: float
    rule_score: float
    features: Optional[List[float]] = None
    feature_details: Optional[Dict[str, Any]] = None
    mfa_required: bool = False
    mfa_method: Optional[str] = None     # "totp" | "email_otp" | None
    revocation_broadcast: bool = False   # True when SSE broadcast was triggered
    ml_timed_out: bool = False           # True if ML inference exceeded SLA
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyUpdate(BaseModel):
    thresholds: Optional[Dict[str, int]] = None
    hard_triggers: Optional[List[str]] = None
    step_up: Optional[Dict[str, Any]] = None
    restrict: Optional[Dict[str, Any]] = None
    mfa_risk_tiers: Optional[Dict[str, Any]] = None


class SimulateRequest(BaseModel):
    identity_id: str = "u_alex"
    scenario: str = "normal"
    count: int = 1
    method: Optional[str] = "POST"
    endpoint: Optional[str] = None
    geo: Optional[str] = None
    device: Optional[str] = None
    payload_size: Optional[int] = None
    token_age_seconds: Optional[float] = None


# ── MFA Models ────────────────────────────────────────────────────────────────

class MFAChallenge(BaseModel):
    """An active MFA challenge bound to a session."""
    session_id: str
    identity_id: str
    method: str                          # "totp" | "email_otp"
    otp_hash: Optional[str] = None       # SHA-256 hash of OTP (email/SMS only)
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempts_remaining: int = 5
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MFATOTPEnrollment(BaseModel):
    """TOTP enrollment record stored per identity."""
    identity_id: str
    encrypted_secret: str                # AES-256-GCM encrypted TOTP seed
    provisioning_uri: str
    backup_codes: List[str] = Field(default_factory=list)
    enrolled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified: bool = False               # True after first successful TOTP verify


class DeviceTrustToken(BaseModel):
    """Time-bound device trust bypass token."""
    token_id: str
    identity_id: str
    device_fingerprint: str              # UA + IP hash
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Session Models ────────────────────────────────────────────────────────────

class SessionRevocationEvent(BaseModel):
    """Audit record for every forced session termination."""
    session_id: str
    identity_id: str
    jti: Optional[str] = None
    reason: str                          # e.g. "impossible_travel", "rate_burst_surge"
    triggered_by: str                    # "ml_engine" | "rule_engine" | "admin_manual"
    ml_confidence: Optional[float] = None
    risk_score: float
    sse_broadcast_success: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Rate Limit Models ─────────────────────────────────────────────────────────

class RateLimitState(BaseModel):
    """Current rate limit state for a key."""
    key: str
    count: int
    window_start: float
    limit: int
    burst_remaining: int
    exceeded: bool
