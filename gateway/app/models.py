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
