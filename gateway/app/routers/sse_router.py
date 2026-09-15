"""
SSE Router — GET /api/events/session

Establishes a Server-Sent Events stream for the authenticated user.
The frontend AuthContext opens this connection on login and listens
for `session_terminated` events to enforce real-time forced logout.

Also exposes:
  GET /api/events/status — connection registry status (admin)
"""
from __future__ import annotations
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth import get_current_user, require_role
from app.config import settings
from app.services.sse_manager import get_sse_manager

router = APIRouter(prefix="/api/events", tags=["sse"])


@router.get("/session")
async def session_events(current_user: dict = Depends(get_current_user)):
    """
    SSE stream for the authenticated session.
    Sends `session_terminated` events when the ML engine or an admin
    forces a session revoke.
    Sends `: ping` keepalive comments every `sse_ping_interval_seconds`.
    """
    identity_id = current_user["identity_id"]
    manager = get_sse_manager()
    queue = await manager.connect(identity_id)

    generator = manager.event_generator(
        identity_id=identity_id,
        queue=queue,
        ping_interval_s=settings.sse_ping_interval_seconds,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering for SSE
            "Connection": "keep-alive",
        },
    )


@router.get("/status")
async def sse_status(current_user: dict = Depends(require_role("admin", "manager"))):
    """Admin: SSE connection registry status."""
    manager = get_sse_manager()
    return {
        "active_connections": manager.active_connection_count(),
        "connected_identities": manager.connected_identities(),
    }
