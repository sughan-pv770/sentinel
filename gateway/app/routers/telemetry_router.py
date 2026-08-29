"""
Simple Telemetry API for Dashboard Updates (Phase 4 Alternative)
Provides polling-based real-time data until SSE can be properly configured.
"""
from __future__ import annotations
from fastapi import APIRouter
from typing import Dict, Any
from datetime import datetime, timezone
from app.state_store import get_store
from app.utils.logger import get_logger
from app.agents import get_health_agent

router = APIRouter(prefix="/sentinelx/telemetry", tags=["telemetry"])
logger = get_logger("sentinelx.telemetry")


@router.get("/metrics")
async def get_current_metrics() -> Dict[str, Any]:
    """Get current system metrics for dashboard."""
    try:
        store = get_store()

        # Get basic stats
        store_stats = await store.stats()
        incident_stats = await store.get_incident_stats()

        # Get health metrics
        health_agent = get_health_agent(store)
        performance_metrics = await health_agent.get_performance_metrics()

        # Get recent activity
        recent_alerts = await store.get_alerts(limit=10)
        recent_incidents = await store.get_incidents(limit=5)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "store": store_stats,
            "incidents": incident_stats,
            "performance": performance_metrics,
            "recent_alerts_count": len(recent_alerts),
            "recent_incidents_count": len(recent_incidents),
            "health_status": "HEALTHY"  # Simplified for now
        }
    except Exception as e:
        logger.error(f"Error getting telemetry metrics: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }