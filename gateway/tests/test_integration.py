"""
Integration tests for agents, incidents, intelligence, and telemetry.

These tests verify that the newly added modules work correctly together.
"""
import pytest
from datetime import datetime, timezone

from app.state_store import InMemoryStore
from app.agents import (
    AnomalyWatcher,
    ThreatTriageAgent,
    PolicyAgent,
    HealthAgent,
    SecurityExplainer,
    get_health_agent
)
from app.incidents import Incident, IncidentManager, IncidentStatus, IncidentSeverity
from app.intelligence import (
    explain_risk,
    calculate_identity_risk,
    calculate_endpoint_risk,
    handle_cold_start,
    get_behavioral_context
)
from app.models import RequestContext, FeatureVector, Reason


@pytest.fixture
def store():
    """Fresh in-memory store for each test."""
    return InMemoryStore()


async def _prime(store, identity_id, endpoint="/profile", geo="US-CA", device="chrome-mac", count=3, ts_base=None):
    """Prime a profile with N requests."""
    ts = ts_base if ts_base is not None else datetime.now(timezone.utc).timestamp()
    for i in range(count):
        await store.record_request(identity_id, endpoint, geo, device, 14, ts + i)


# ═══════════════════════════════════════════════════════════
# AGENT TESTS
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_anomaly_watcher_detects_traffic_spike(store):
    """Test that AnomalyWatcher detects traffic spikes."""
    watcher = AnomalyWatcher(store)

    now = datetime.now(timezone.utc).timestamp()
    for i in range(35):
        await store.record_request("u_burst", "/api", "US-CA", "chrome", 14, now + i)

    spike_detected, message = await watcher.detect_traffic_spike("u_burst")
    assert spike_detected is True
    assert "req/min" in message


@pytest.mark.asyncio
async def test_anomaly_watcher_no_spike_for_normal_traffic(store):
    """Test that normal traffic doesn't trigger spike detection."""
    await _prime(store, "u_test", count=3)
    watcher = AnomalyWatcher(store)
    spike_detected, message = await watcher.detect_traffic_spike("u_test")
    assert spike_detected is False
    assert message is None


@pytest.mark.asyncio
async def test_threat_triage_classifies_severity(store):
    """Test that ThreatTriageAgent correctly classifies threats."""
    await _prime(store, "u_test", count=3)
    agent = ThreatTriageAgent(store)

    reasons = [Reason(code="privilege_escalation_attempt", message="Admin access attempt")]
    severity, threat_type, evidence = await agent.analyze_threat_level(
        "u_test", 85.0, reasons, True
    )

    assert severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert threat_type == "PRIVILEGE_ESCALATION"
    assert len(evidence) > 0


@pytest.mark.asyncio
async def test_policy_agent_recommends_revoke(store):
    """Test that PolicyAgent recommends correct action for high risk."""
    agent = PolicyAgent(store)

    recommendation = await agent.recommend_action(
        risk_score=90.0,
        tier="revoke",
        threat_type="TOKEN_REUSE_ATTACK",
        identity_id="u_test"
    )

    assert recommendation["action"] == "REVOKE_SESSION"
    assert "rationale" in recommendation
    assert "additional_steps" in recommendation


@pytest.mark.asyncio
async def test_health_agent_checks_system(store):
    """Test that HealthAgent performs health checks."""
    agent = HealthAgent(store)

    health = await agent.check_system_health()

    assert "status" in health
    assert "components" in health
    assert "store" in health["components"]
    assert "ml_engine" in health["components"]


@pytest.mark.asyncio
async def test_health_agent_tracks_latency(store):
    """Test that HealthAgent tracks latency metrics."""
    agent = HealthAgent(store)

    agent.track_latency(10.5)
    agent.track_latency(12.3)
    agent.track_latency(9.8)

    metrics = await agent.get_performance_metrics()

    assert "average_latency_ms" in metrics
    assert "p95_latency_ms" in metrics
    assert metrics["sample_count"] == 3


def test_security_explainer_generates_explanations():
    """Test that SecurityExplainer creates clear explanations."""
    reasons = [
        Reason(code="frequency_spike", message="Unusual request rate"),
        Reason(code="new_endpoint", message="First time accessing endpoint")
    ]

    explanation = SecurityExplainer.explain_decision(
        risk_score=65.0,
        tier="restrict",
        reasons=reasons,
        ml_score=45.0,
        rule_score=20.0
    )

    assert "summary" in explanation
    assert "risk_level" in explanation
    assert "why_flagged" in explanation
    assert explanation["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert len(explanation["why_flagged"]) > 0


@pytest.mark.asyncio
async def test_health_agent_singleton(store):
    """Test that get_health_agent returns singleton."""
    agent1 = get_health_agent(store)
    agent2 = get_health_agent(store)
    assert agent1 is agent2


# ═══════════════════════════════════════════════════════════
# INCIDENT TESTS
# ═══════════════════════════════════════════════════════════

def test_incident_creation():
    """Test creating a new incident."""
    incident = Incident(
        identity_id="u_test",
        endpoint="/admin",
        risk_score=85.0,
        ml_score=60.0,
        rule_score=25.0,
        reasons=["Privilege escalation attempt"],
        action_taken="RESTRICTED",
        severity=IncidentSeverity.HIGH
    )

    assert incident.incident_id.startswith("INC-")
    assert incident.status == IncidentStatus.OPEN
    assert len(incident.timeline) == 1
    assert incident.severity == IncidentSeverity.HIGH


def test_incident_status_update():
    """Test updating incident status."""
    incident = Incident(
        identity_id="u_test",
        endpoint="/api",
        risk_score=70.0,
        ml_score=50.0,
        rule_score=20.0,
        reasons=["Anomalous behavior"],
        action_taken="STEP_UP",
        severity=IncidentSeverity.MEDIUM
    )

    incident.update_status(IncidentStatus.INVESTIGATING, "Security team notified")

    assert incident.status == IncidentStatus.INVESTIGATING
    assert len(incident.timeline) == 2
    assert incident.timeline[1]["event"] == "status_changed"


def test_incident_to_dict():
    """Test incident serialization."""
    incident = Incident(
        identity_id="u_test",
        endpoint="/api",
        risk_score=75.0,
        ml_score=55.0,
        rule_score=20.0,
        reasons=["Test reason"],
        action_taken="RESTRICTED"
    )

    data = incident.to_dict()

    assert data["incident_id"] == incident.incident_id
    assert data["identity_id"] == "u_test"
    assert data["risk_score"] == 75.0
    assert data["status"] == "OPEN"


def test_incident_from_dict():
    """Test incident deserialization."""
    data = {
        "incident_id": "INC-TEST123",
        "identity_id": "u_test",
        "endpoint": "/api",
        "risk_score": 75.0,
        "ml_score": 55.0,
        "rule_score": 20.0,
        "reasons": ["Test"],
        "action_taken": "RESTRICTED",
        "severity": "HIGH",
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "timeline": [],
        "metadata": {}
    }

    incident = Incident.from_dict(data)

    assert incident.incident_id == "INC-TEST123"
    assert incident.identity_id == "u_test"
    assert incident.severity == IncidentSeverity.HIGH


@pytest.mark.asyncio
async def test_incident_manager_should_create_incident(store):
    """Test incident creation logic."""
    manager = IncidentManager(store)

    assert manager.should_create_incident(75.0, "restrict", True) is True
    assert manager.should_create_incident(20.0, "allow", False) is False


@pytest.mark.asyncio
async def test_incident_manager_determine_severity(store):
    """Test severity determination."""
    manager = IncidentManager(store)

    severity = manager.determine_severity(95.0, "revoke", [])
    assert severity == IncidentSeverity.CRITICAL

    severity = manager.determine_severity(45.0, "step_up", [])
    assert severity == IncidentSeverity.MEDIUM


@pytest.mark.asyncio
async def test_incident_manager_create_and_retrieve(store):
    """Test creating and retrieving incidents."""
    manager = IncidentManager(store)

    reasons = [Reason(code="test", message="Test reason")]
    incident = await manager.create_incident(
        identity_id="u_test",
        endpoint="/admin",
        risk_score=85.0,
        ml_score=60.0,
        rule_score=25.0,
        reasons=reasons,
        tier="restrict",
        action="RESTRICTED"
    )

    retrieved = await manager.get_incident(incident.incident_id)
    assert retrieved is not None
    assert retrieved.incident_id == incident.incident_id


@pytest.mark.asyncio
async def test_incident_manager_get_recent(store):
    """Test retrieving recent incidents."""
    manager = IncidentManager(store)

    for i in range(3):
        await manager.create_incident(
            identity_id=f"u_test{i}",
            endpoint="/api",
            risk_score=70.0 + i * 5,
            ml_score=50.0,
            rule_score=20.0,
            reasons=[],
            tier="step_up",
            action="STEP_UP"
        )

    incidents = await manager.get_recent_incidents(limit=10)
    assert len(incidents) == 3


@pytest.mark.asyncio
async def test_incident_manager_update_status(store):
    """Test updating incident status."""
    manager = IncidentManager(store)

    incident = await manager.create_incident(
        identity_id="u_test",
        endpoint="/api",
        risk_score=75.0,
        ml_score=55.0,
        rule_score=20.0,
        reasons=[],
        tier="restrict",
        action="RESTRICTED"
    )

    success = await manager.update_incident_status(
        incident.incident_id,
        "INVESTIGATING",
        "Team notified"
    )

    assert success is True

    updated = await manager.get_incident(incident.incident_id)
    assert updated.status == IncidentStatus.INVESTIGATING


@pytest.mark.asyncio
async def test_incident_stats(store):
    """Test incident statistics."""
    manager = IncidentManager(store)

    await manager.create_incident(
        identity_id="u_test1",
        endpoint="/api",
        risk_score=95.0,
        ml_score=70.0,
        rule_score=25.0,
        reasons=[],
        tier="revoke",
        action="REVOKED"
    )

    await manager.create_incident(
        identity_id="u_test2",
        endpoint="/api",
        risk_score=75.0,
        ml_score=55.0,
        rule_score=20.0,
        reasons=[],
        tier="restrict",
        action="RESTRICTED"
    )

    stats = await manager.get_incident_stats()

    assert stats["total_incidents"] == 2
    assert stats["open_incidents"] >= 0
    assert "critical_incidents" in stats


# ═══════════════════════════════════════════════════════════
# INTELLIGENCE TESTS
# ═══════════════════════════════════════════════════════════

def test_calculate_identity_risk_cold_start():
    """Test identity risk calculation for new users."""
    profile = {"total": 2, "endpoints": {}, "geos": {}, "devices": {}}

    risk_score, risk_level = calculate_identity_risk(profile, [])

    assert risk_score == 0.0
    assert risk_level == "UNKNOWN"


def test_calculate_identity_risk_established():
    """Test identity risk calculation for established users."""
    profile = {
        "total": 50,
        "endpoints": {f"/api/{i}": 2 for i in range(15)},
        "geos": {"US-CA": 40, "US-NY": 5, "UK-LN": 3, "FR-PR": 2},
        "devices": {"chrome-mac": 45, "firefox-win": 3, "safari-ios": 2}
    }

    decisions = [
        {"risk_score": 70},
        {"risk_score": 65},
        {"risk_score": 80}
    ]

    risk_score, risk_level = calculate_identity_risk(profile, decisions)

    assert risk_score > 0
    assert risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _make_ctx_for_risk(endpoint: str, method: str = "GET", service: str = "demo-service") -> RequestContext:
    return RequestContext(
        service=service,
        identity_id="u_test",
        session_id="sess_1",
        endpoint=endpoint,
        method=method,
        ip="10.0.0.1",
        geo="IN-TN",
        device="chrome-mac",
        token_age_seconds=600.0,
        payload_size=100,
    )


def test_calculate_endpoint_risk():
    """Test endpoint risk classification."""
    score, level = calculate_endpoint_risk(_make_ctx_for_risk("/admin/users"))
    assert level == "CRITICAL"
    assert score >= 85

    score, level = calculate_endpoint_risk(_make_ctx_for_risk("/payments/transfer"))
    assert level == "HIGH"
    assert score >= 70

    score, level = calculate_endpoint_risk(_make_ctx_for_risk("/health"))
    assert level == "LOW"
    assert score <= 15


def test_handle_cold_start():
    """Test cold start handling."""
    profile = {"total": 2}
    info = handle_cold_start(None, profile)

    assert info["is_cold_start"] is True
    assert info["confidence_level"] == "LOW"
    assert info["baseline_sufficient"] is False

    profile = {"total": 15}
    info = handle_cold_start(None, profile)

    assert info["is_cold_start"] is False
    assert info["confidence_level"] in ["MEDIUM", "HIGH"]
    assert info["baseline_sufficient"] is True


def test_get_behavioral_context():
    """Test behavioral context generation."""
    profile = {
        "total": 25,
        "endpoints": {"/api": 15, "/profile": 10},
        "geos": {"US-CA": 20, "US-NY": 5},
        "devices": {"chrome-mac": 25}
    }

    ctx = RequestContext(
        service="orbit",
        identity_id="u_test",
        session_id="sess_1",
        endpoint="/api",
        method="GET",
        ip="10.0.0.1",
        geo="US-CA",
        device="chrome-mac",
        token_age_seconds=600.0,
        payload_size=100
    )

    context = get_behavioral_context(ctx, profile)

    assert context["total_requests"] == 25
    assert context["unique_endpoints"] == 2
    assert context["most_common_endpoint"] == "/api"
    assert context["is_established"] is True


def test_explain_risk():
    """Test risk explanation generation."""
    ctx = RequestContext(
        service="orbit",
        identity_id="u_test",
        session_id="sess_1",
        endpoint="/admin",
        method="POST",
        ip="10.0.0.1",
        geo="RU-MOW",
        device="unknown",
        token_age_seconds=30.0,
        payload_size=5000
    )

    fv = FeatureVector(
        request_frequency_per_min=25.0,
        endpoint_novelty=1.0,
        geo_change=1.0,
        device_change=1.0,
        time_of_day_deviation=2.0,
        payload_size_zscore=3.5,
        token_age_seconds=30.0
    )

    reasons = [
        Reason(code="privilege_escalation", message="Admin endpoint access")
    ]

    profile = {"total": 20, "endpoints": {"/api": 20}, "geos": {"US-CA": 20}, "devices": {"chrome": 20}}

    explanations = explain_risk(ctx, fv, 65.0, 30.0, reasons, profile)

    assert len(explanations) > 0
    assert any("Admin endpoint access" in exp for exp in explanations)
