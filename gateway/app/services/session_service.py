"""
Session lifecycle service — creation, validation, and revocation.

Centralises all session-related business logic so routers stay thin.
Triggers the SSE broadcast when a session is force-terminated.
"""
from __future__ import annotations
import time
import uuid
from typing import Optional, List

from app.auth import create_access_token, create_refresh_token
from app.services.sse_manager import get_sse_manager
from app.utils.logger import get_logger

logger = get_logger("sentinelx.session_service")


async def create_session(identity_id: str, role: str, store) -> dict:
    """
    Create a new authenticated session.
    Issues access + refresh tokens and registers the session.
    """
    jti = str(uuid.uuid4())
    session_id = f"sess_{identity_id}_{jti[:8]}"

    access_token = create_access_token(
        {"sub": identity_id, "role": role, "jti": jti, "session_id": session_id}
    )
    refresh_token = create_refresh_token(identity_id, jti)

    await store.register_active_session(identity_id, session_id, jti)

    logger.info(f"Session created  identity={identity_id}  session_id={session_id}  jti={jti[:8]}...")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "session_id": session_id,
        "jti": jti,
    }


async def revoke_session_and_broadcast(
    identity_id: str,
    session_id: str,
    jti: Optional[str],
    reason: str,
    risk_score: float,
    triggered_by: str,
    store,
) -> dict:
    """
    Revoke a single session and broadcast the SSE termination event.
    Used for targeted revocation of a specific session.
    """
    from app.config import settings

    # Revoke in store
    await store.revoke_session(session_id)
    if jti:
        await store.revoke_jti(jti, ttl_seconds=settings.jwt_expire_minutes * 60 + 60)

    # SSE broadcast
    sse = get_sse_manager()
    notified = await sse.broadcast_termination(
        identity_id=identity_id,
        reason=reason,
        risk_score=risk_score,
        triggered_by=triggered_by,
    )

    # Audit log
    audit_event = {
        "session_id": session_id,
        "identity_id": identity_id,
        "jti": jti,
        "reason": reason,
        "triggered_by": triggered_by,
        "risk_score": risk_score,
        "sse_broadcast_success": notified > 0,
        "connections_notified": notified,
        "timestamp": time.time(),
    }
    await store.add_revocation_audit(audit_event)

    logger.warning(
        f"Session revoked  identity={identity_id}  session={session_id}  "
        f"reason={reason}  sse_notified={notified}"
    )
    return audit_event


async def revoke_all_sessions_and_broadcast(
    identity_id: str,
    reason: str,
    risk_score: float,
    triggered_by: str,
    store,
) -> dict:
    """
    Revoke ALL sessions for an identity and broadcast SSE termination.
    Used by the ML engine for critical-tier decisions (risk ≥ 85).
    """
    revoked_ids = await store.revoke_all_user_sessions(identity_id)

    sse = get_sse_manager()
    notified = await sse.broadcast_termination(
        identity_id=identity_id,
        reason=reason,
        risk_score=risk_score,
        triggered_by=triggered_by,
    )

    audit_event = {
        "identity_id": identity_id,
        "revoked_sessions": revoked_ids,
        "revoked_count": len(revoked_ids),
        "reason": reason,
        "triggered_by": triggered_by,
        "risk_score": risk_score,
        "sse_broadcast_success": notified > 0,
        "connections_notified": notified,
        "timestamp": time.time(),
    }
    await store.add_revocation_audit(audit_event)

    logger.warning(
        f"ALL sessions revoked  identity={identity_id}  count={len(revoked_ids)}  "
        f"reason={reason}  sse_notified={notified}"
    )
    return audit_event
