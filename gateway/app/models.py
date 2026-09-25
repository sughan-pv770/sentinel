from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


class RequestContext(BaseModel):
    service: str = "orbit"
    identity_id: str
    session_id: str
    endpoint: str
    method: str
    ip: str
    geo: str
    device: str
    token_age_seconds: float
    payload_size: int
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
    model_config = {"protected_namespaces": ()}
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
    contributions: Optional[List[float]] = None
    model_version: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyUpdate(BaseModel):
    thresholds: Optional[Dict[str, int]] = None
    hard_triggers: Optional[List[str]] = None
    step_up: Optional[Dict[str, Any]] = None
    restrict: Optional[Dict[str, Any]] = None


class SimulateRequest(BaseModel):
    identity_id: str = "u_alex"
    scenario: str = "normal"  # normal | frequency_spike | new_admin_endpoint | impossible_travel | privilege_escalation | custom
    count: int = 1
    method: Optional[str] = "POST"
    endpoint: Optional[str] = None
    geo: Optional[str] = None
    device: Optional[str] = None
    payload_size: Optional[int] = None
    token_age_seconds: Optional[float] = None
    nonce: Optional[str] = None


# ════════════════════════════════════════════════════════════════
# Collective Immune System (Shared Threat-Signal Network) Models
# ════════════════════════════════════════════════════════════════

class ThreatSignal(BaseModel):
    signal_id: str
    identity_hash: str                  # SHA-256 one-way hash of identity_id (0% PII)
    gateway_id: str                     # Source gateway instance ID
    gateway_name: str                   # Human-readable peer gateway name
    verdict_tier: str                   # "REVOKE" | "RESTRICT" only
    severity: str = "HIGH"              # "CRITICAL" | "HIGH"
    reason_category: str = "credential_compromise"
    timestamp: float
    iso_time: str
    is_simulated_peer: bool = False


class ThreatSignalSubmission(BaseModel):
    identity_hash: str                  # 64-char hex SHA-256
    verdict_tier: str                   # "REVOKE" | "RESTRICT"
    gateway_id: Optional[str] = None
    gateway_name: Optional[str] = None
    reason_category: Optional[str] = "credential_compromise"
    severity: Optional[str] = None


class SimulatePeerSignalRequest(BaseModel):
    identity_id: str = "u_alex"
    peer_gateway_id: str = "gateway-nexus-erp"
    peer_gateway_name: str = "Gateway Alpha (Nexus ERP)"
    verdict_tier: str = "REVOKE"
    reason_category: str = "credential_stuffing_detected"

