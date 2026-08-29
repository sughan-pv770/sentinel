"""
Incident Management System

Tracks security incidents from detection through resolution.
Each incident represents a cluster of related anomalies or a significant security event.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from enum import Enum


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Incident:
    """Represents a security incident."""

    def __init__(
        self,
        identity_id: str,
        endpoint: str,
        risk_score: float,
        ml_score: float,
        rule_score: float,
        reasons: List[str],
        action_taken: str,
        severity: IncidentSeverity = IncidentSeverity.MEDIUM
    ):
        self.incident_id = f"INC-{uuid.uuid4().hex[:12].upper()}"
        self.identity_id = identity_id
        self.endpoint = endpoint
        self.risk_score = risk_score
        self.ml_score = ml_score
        self.rule_score = rule_score
        self.reasons = reasons
        self.action_taken = action_taken
        self.severity = severity
        self.status = IncidentStatus.OPEN
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.timeline: List[Dict] = [{
            "timestamp": self.created_at.isoformat(),
            "event": "incident_created",
            "details": f"Incident created for {identity_id} accessing {endpoint}"
        }]
        self.metadata: Dict = {}

    def update_status(self, new_status: IncidentStatus, note: str = ""):
        """Update incident status and add timeline entry."""
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self.timeline.append({
            "timestamp": self.updated_at.isoformat(),
            "event": "status_changed",
            "details": f"Status changed to {new_status.value}",
            "note": note
        })

    def add_event(self, event_type: str, details: str):
        """Add a timeline event to the incident."""
        self.updated_at = datetime.now(timezone.utc)
        self.timeline.append({
            "timestamp": self.updated_at.isoformat(),
            "event": event_type,
            "details": details
        })

    def to_dict(self) -> Dict:
        """Convert incident to dictionary for API/storage."""
        return {
            "incident_id": self.incident_id,
            "identity_id": self.identity_id,
            "endpoint": self.endpoint,
            "risk_score": self.risk_score,
            "ml_score": self.ml_score,
            "rule_score": self.rule_score,
            "reasons": self.reasons,
            "action_taken": self.action_taken,
            "severity": self.severity.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "timeline": self.timeline,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Incident':
        """Create incident from dictionary."""
        incident = cls.__new__(cls)
        incident.incident_id = data["incident_id"]
        incident.identity_id = data["identity_id"]
        incident.endpoint = data["endpoint"]
        incident.risk_score = data["risk_score"]
        incident.ml_score = data["ml_score"]
        incident.rule_score = data["rule_score"]
        incident.reasons = data["reasons"]
        incident.action_taken = data["action_taken"]
        incident.severity = IncidentSeverity(data["severity"])
        incident.status = IncidentStatus(data["status"])
        incident.created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        incident.updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        incident.timeline = data["timeline"]
        incident.metadata = data.get("metadata", {})
        return incident


class IncidentManager:
    """Manages incident creation, tracking, and retrieval."""

    def __init__(self, store):
        self.store = store

    def should_create_incident(self, risk_score: float, tier: str, rule_triggered: bool) -> bool:
        """Determine if a request should trigger incident creation."""
        # Create incident for high-risk decisions
        if risk_score >= 70:
            return True
        # Create incident for any hard rule trigger
        if rule_triggered:
            return True
        # Create incident for restricted or revoked actions
        if tier in ["restrict", "revoke"]:
            return True
        return False

    def determine_severity(self, risk_score: float, tier: str, reasons: List) -> IncidentSeverity:
        """Determine incident severity based on risk factors."""
        if risk_score >= 90 or tier == "revoke":
            return IncidentSeverity.CRITICAL
        if risk_score >= 70 or tier == "restrict":
            return IncidentSeverity.HIGH
        if risk_score >= 50 or tier == "step_up":
            return IncidentSeverity.MEDIUM
        return IncidentSeverity.LOW

    async def create_incident(
        self,
        identity_id: str,
        endpoint: str,
        risk_score: float,
        ml_score: float,
        rule_score: float,
        reasons: List,
        tier: str,
        action: str
    ) -> Incident:
        """Create and store a new security incident."""
        severity = self.determine_severity(risk_score, tier, reasons)

        reason_messages = [r.message if hasattr(r, 'message') else str(r) for r in reasons]

        incident = Incident(
            identity_id=identity_id,
            endpoint=endpoint,
            risk_score=risk_score,
            ml_score=ml_score,
            rule_score=rule_score,
            reasons=reason_messages,
            action_taken=action,
            severity=severity
        )

        await self.store.add_incident(incident.to_dict())
        return incident

    async def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Retrieve a specific incident by ID."""
        data = await self.store.get_incident(incident_id)
        if data:
            return Incident.from_dict(data)
        return None

    async def get_recent_incidents(self, limit: int = 50, severity: Optional[str] = None) -> List[Incident]:
        """Retrieve recent incidents, optionally filtered by severity."""
        incidents_data = await self.store.get_incidents(limit=limit, severity=severity)
        return [Incident.from_dict(data) for data in incidents_data]

    async def update_incident_status(self, incident_id: str, new_status: str, note: str = "") -> bool:
        """Update the status of an incident."""
        incident = await self.get_incident(incident_id)
        if incident:
            incident.update_status(IncidentStatus(new_status), note)
            await self.store.update_incident(incident.to_dict())
            return True
        return False

    async def get_incidents_by_identity(self, identity_id: str, limit: int = 20) -> List[Incident]:
        """Get all incidents for a specific identity."""
        incidents_data = await self.store.get_incidents_by_identity(identity_id, limit=limit)
        return [Incident.from_dict(data) for data in incidents_data]

    async def get_incident_stats(self) -> Dict:
        """Get incident statistics."""
        return await self.store.get_incident_stats()
