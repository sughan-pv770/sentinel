"""
Incident Management API Router

Provides endpoints for:
- Creating incidents
- Retrieving incidents
- Updating incident status
- Querying incidents by identity
- Incident statistics
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from typing import Optional
from app.state_store import get_store
from app.incidents import IncidentManager, IncidentStatus
from app.utils.logger import get_logger

router = APIRouter(prefix="/sentinelx/incidents", tags=["incidents"])
logger = get_logger("sentinelx.incidents")


@router.get("/")
async def get_incidents(limit: int = 50, severity: Optional[str] = None):
    """Retrieve recent incidents, optionally filtered by severity."""
    store = get_store()
    manager = IncidentManager(store)
    incidents = await manager.get_recent_incidents(limit=limit, severity=severity)
    return {"incidents": [inc.to_dict() for inc in incidents], "count": len(incidents)}


@router.get("/{incident_id}")
async def get_incident_detail(incident_id: str):
    """Retrieve detailed information about a specific incident."""
    store = get_store()
    manager = IncidentManager(store)
    incident = await manager.get_incident(incident_id)

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return incident.to_dict()


@router.post("/{incident_id}/status")
async def update_incident_status(incident_id: str, status: str, note: str = ""):
    """Update the status of an incident."""
    try:
        # Validate status
        IncidentStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    store = get_store()
    manager = IncidentManager(store)
    success = await manager.update_incident_status(incident_id, status, note)

    if not success:
        raise HTTPException(status_code=404, detail="Incident not found")

    return {"incident_id": incident_id, "status": status, "updated": True}


@router.get("/identity/{identity_id}")
async def get_incidents_by_identity(identity_id: str, limit: int = 20):
    """Retrieve all incidents for a specific identity."""
    store = get_store()
    manager = IncidentManager(store)
    incidents = await manager.get_incidents_by_identity(identity_id, limit=limit)
    return {
        "identity_id": identity_id,
        "incidents": [inc.to_dict() for inc in incidents],
        "count": len(incidents)
    }


@router.get("/stats/summary")
async def get_incident_statistics():
    """Get incident statistics summary."""
    store = get_store()
    manager = IncidentManager(store)
    stats = await manager.get_incident_stats()
    return stats
