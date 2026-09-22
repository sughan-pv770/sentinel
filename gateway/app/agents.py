"""
Security Agents - Automated Security Analysis & Response

Lightweight backend workers that monitor, analyze, and respond to security events:
1. Anomaly Watcher - Detects traffic spikes and deviations
2. Threat Triage Agent - Groups related anomalies into incidents
3. Policy Agent - Recommends security actions
4. Incident Response Agent - Automates incident creation/updates
5. Health Agent - Monitors system health
6. Security Explainer - Converts technical signals to human explanations
"""
from __future__ import annotations
import asyncio
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from app.utils.logger import get_logger

logger = get_logger("sentinelx.agents")


class AnomalyWatcher:
    """
    Monitors incoming traffic for anomalies:
    - Traffic spikes
    - Behavioral deviations
    - Suspicious patterns
    """

    def __init__(self, store):
        self.store = store
        self.baseline_window = 300  # 5 minutes

    async def detect_traffic_spike(self, identity_id: str) -> Tuple[bool, Optional[str]]:
        """Detect if identity is experiencing unusual traffic spike."""
        profile = await self.store.get_profile(identity_id)
        timestamps = profile.get("timestamps", [])

        if not timestamps or len(timestamps) < 5:
            return False, None

        # Check requests in last minute
        now = datetime.now(timezone.utc).timestamp()
        recent = [t for t in timestamps if now - t <= 60]
        rate = len(recent)

        # Compare to historical average
        if len(timestamps) > 10:
            # Calculate typical rate
            older_timestamps = [t for t in timestamps if now - t > 120]
            if older_timestamps:
                typical_rate = len(older_timestamps) / max((timestamps[0] - timestamps[-1]) / 60, 1)
                if rate > typical_rate * 5:  # 5x spike
                    return True, f"Traffic spike detected: {rate} req/min (typical: {typical_rate:.1f} req/min)"

        # Absolute threshold
        if rate > 30:
            return True, f"High request rate: {rate} req/min"

        return False, None

    async def detect_behavioral_deviation(self, identity_id: str) -> Tuple[bool, List[str]]:
        """Detect if identity behavior has deviated from baseline."""
        profile = await self.store.get_profile(identity_id)
        recent_decisions = await self.store.get_recent_decisions(identity_id, limit=5)
        deviations = []

        # Check for multiple high-risk decisions
        if recent_decisions:
            high_risk = [d for d in recent_decisions if d.get("risk_score", 0) > 60]
            if len(high_risk) >= 3:
                deviations.append(f"{len(high_risk)} high-risk decisions in recent activity")

        # Check for unusual endpoint access
        endpoints = profile.get("endpoints", {})
        if len(endpoints) > 15:
            deviations.append(f"Accessing {len(endpoints)} different endpoints")

        # Check for geographic diversity
        geos = profile.get("geos", {})
        if len(geos) > 4:
            deviations.append(f"Activity from {len(geos)} different locations")

        return len(deviations) > 0, deviations


class ThreatTriageAgent:
    """
    Groups related anomalies and determines severity.
    Analyzes multiple signals to classify threats.
    """

    def __init__(self, store):
        self.store = store

    async def analyze_threat_level(
        self,
        identity_id: str,
        risk_score: float,
        reasons: List,
        rule_triggered: bool
    ) -> Tuple[str, str, List[str]]:
        """
        Analyze and classify threat level.
        Returns: (severity, threat_type, evidence)
        """
        evidence = []
        threat_type = "UNKNOWN"

        # Analyze reasons
        reason_codes = [r.code if hasattr(r, 'code') else str(r) for r in reasons]

        if "token_used_after_revocation" in reason_codes:
            threat_type = "TOKEN_REUSE_ATTACK"
            evidence.append("Revoked token reused")
            severity = "CRITICAL"
        elif "privilege_escalation_attempt" in reason_codes:
            threat_type = "PRIVILEGE_ESCALATION"
            evidence.append("Attempt to access sensitive endpoint")
            severity = "HIGH"
        elif "impossible_travel" in reason_codes:
            threat_type = "ACCOUNT_TAKEOVER"
            evidence.append("Impossible geographic travel detected")
            severity = "HIGH"
        elif "frequency_spike" in reason_codes:
            threat_type = "BRUTE_FORCE"
            evidence.append("Unusual request frequency")
            severity = "MEDIUM"
        elif risk_score > 75:
            threat_type = "ANOMALOUS_BEHAVIOR"
            evidence.append(f"High anomaly score: {risk_score}")
            severity = "HIGH"
        else:
            threat_type = "SUSPICIOUS_ACTIVITY"
            evidence.append("Behavioral deviation from baseline")
            severity = "MEDIUM"

        # Add recent history context
        recent = await self.store.get_recent_decisions(identity_id, limit=10)
        if recent:
            high_risk_count = sum(1 for d in recent if d.get("risk_score", 0) > 60)
            if high_risk_count > 0:
                evidence.append(f"{high_risk_count} high-risk decisions in recent history")

        return severity, threat_type, evidence


class PolicyAgent:
    """
    Recommends security actions based on risk analysis.
    Uses existing policy engine to suggest responses.
    """

    def __init__(self, store):
        self.store = store

    async def recommend_action(
        self,
        risk_score: float,
        tier: str,
        threat_type: str,
        identity_id: str
    ) -> Dict[str, str]:
        """
        Recommend security action based on risk assessment.
        Returns: {action, rationale, additional_steps}
        """
        policy = await self.store.get_policy()

        if tier == "revoke":
            return {
                "action": "REVOKE_SESSION",
                "rationale": f"Risk score {risk_score} exceeds revoke threshold. Threat type: {threat_type}",
                "additional_steps": "Notify security team immediately. Investigate for account compromise."
            }
        elif tier == "restrict":
            return {
                "action": "RESTRICT_ACCESS",
                "rationale": f"Risk score {risk_score} indicates suspicious activity",
                "additional_steps": "Rate-limit requests. Monitor for escalation. Consider temporary MFA."
            }
        elif tier == "step_up":
            return {
                "action": "REQUIRE_MFA",
                "rationale": f"Moderate risk ({risk_score}) requires additional verification",
                "additional_steps": "Challenge with MFA. Update behavioral baseline after successful auth."
            }
        else:
            return {
                "action": "ALLOW_WITH_MONITORING",
                "rationale": "Risk within acceptable threshold",
                "additional_steps": "Continue monitoring behavioral patterns"
            }


class HealthAgent:
    """
    Monitors system health and performance.
    Tracks gateway, origin, database, ML engine status.
    """

    def __init__(self, store):
        self.store = store
        self.metrics = defaultdict(list)

    async def check_system_health(self) -> Dict[str, any]:
        """Perform comprehensive system health check."""
        health = {
            "status": "HEALTHY",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }

        # Check store
        try:
            stats = await self.store.stats()
            health["components"]["store"] = {
                "status": "UP",
                "backend": stats.get("backend"),
                "identities_tracked": stats.get("identities_tracked", 0)
            }
        except Exception as e:
            health["components"]["store"] = {"status": "DOWN", "error": str(e)}
            health["status"] = "DEGRADED"

        # Check ML engine
        try:
            from app.ml_engine import get_ml_engine
            engine = get_ml_engine()
            health["components"]["ml_engine"] = {
                "status": "UP",
                "model_loaded": engine.model is not None
            }
        except Exception as e:
            health["components"]["ml_engine"] = {"status": "DOWN", "error": str(e)}
            health["status"] = "DEGRADED"

        # Check alerts/incidents
        try:
            alerts = await self.store.get_alerts(limit=10)
            incidents = await self.store.get_incidents(limit=10)
            health["components"]["security"] = {
                "status": "UP",
                "recent_alerts": len(alerts),
                "recent_incidents": len(incidents)
            }
        except Exception as e:
            health["components"]["security"] = {"status": "DOWN", "error": str(e)}

        return health

    def track_latency(self, latency_ms: float):
        """Track request latency for performance monitoring."""
        self.metrics["latency"].append(latency_ms)
        # Keep only last 100 measurements
        if len(self.metrics["latency"]) > 100:
            self.metrics["latency"].pop(0)

    async def get_performance_metrics(self) -> Dict:
        """Get performance metrics summary."""
        latencies = self.metrics.get("latency", [])
        if not latencies:
            return {"average_latency_ms": 0, "p95_latency_ms": 0}

        sorted_lat = sorted(latencies)
        avg = sum(sorted_lat) / len(sorted_lat)
        p95_idx = int(len(sorted_lat) * 0.95)
        p95 = sorted_lat[p95_idx] if p95_idx < len(sorted_lat) else sorted_lat[-1]

        return {
            "average_latency_ms": round(avg, 2),
            "p95_latency_ms": round(p95, 2),
            "sample_count": len(latencies)
        }


class SecurityExplainer:
    """
    Converts technical security signals into clear explanations.
    Makes risk decisions understandable to non-technical users.
    """

    @staticmethod
    def explain_decision(
        risk_score: float,
        tier: str,
        reasons: List,
        ml_score: float,
        rule_score: float
    ) -> Dict[str, any]:
        """Generate human-readable explanation of security decision."""
        explanation = {
            "summary": "",
            "risk_level": "",
            "why_flagged": [],
            "technical_details": {
                "risk_score": risk_score,
                "ml_score": ml_score,
                "rule_score": rule_score,
                "tier": tier
            },
            "user_impact": ""
        }

        # Determine risk level
        if risk_score >= 85:
            explanation["risk_level"] = "CRITICAL"
            explanation["summary"] = "Severe security threat detected"
        elif risk_score >= 60:
            explanation["risk_level"] = "HIGH"
            explanation["summary"] = "Significant security concern identified"
        elif risk_score >= 30:
            explanation["risk_level"] = "MEDIUM"
            explanation["summary"] = "Unusual activity detected"
        else:
            explanation["risk_level"] = "LOW"
            explanation["summary"] = "Activity within normal parameters"

        # Extract why it was flagged
        for reason in reasons:
            if hasattr(reason, 'message'):
                explanation["why_flagged"].append(reason.message)
            else:
                explanation["why_flagged"].append(str(reason))

        # Explain user impact
        if tier == "revoke":
            explanation["user_impact"] = "Access blocked. Session terminated for security."
        elif tier == "restrict":
            explanation["user_impact"] = "Access limited. Reduced permissions applied."
        elif tier == "step_up":
            explanation["user_impact"] = "Additional verification required (MFA)."
        else:
            explanation["user_impact"] = "Request allowed. No action needed."

        return explanation


# Singleton instances
_health_agent: Optional[HealthAgent] = None


def get_health_agent(store) -> HealthAgent:
    """Get or create health agent singleton."""
    global _health_agent
    if _health_agent is None:
        _health_agent = HealthAgent(store)
    return _health_agent
