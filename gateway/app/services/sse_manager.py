"""
SSE (Server-Sent Events) Connection Manager.

Maintains an in-process registry of active SSE connections per identity.
When the decision engine issues a revoke verdict, it calls
`sse_manager.broadcast_termination(identity_id, ...)` which pushes
a `session_terminated` event to every open SSE stream for that user.

The frontend AuthContext listens on `GET /api/events/session` and calls
`logout()` immediately upon receiving this event — enforcing real-time
session termination regardless of token expiry.

Design notes:
  - asyncio.Queue per connection (not per identity) for back-pressure.
  - Each queue holds at most MAX_QUEUE_SIZE events; overflow is dropped
    (the client will be logged out on the next API call anyway via JTI check).
  - Connection cleanup is automatic: SSE endpoint generator removes its
    queue from the registry when the client disconnects.
"""
from __future__ import annotations
import asyncio
import json
import time
from collections import defaultdict
from typing import AsyncGenerator, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger("sentinelx.sse_manager")

MAX_QUEUE_SIZE = 10  # Maximum buffered events per connection


class SSEManager:
    """
    In-process SSE connection registry.

    Thread-safety: all mutations happen inside the asyncio event loop;
    no cross-thread access is needed for an async FastAPI application.
    """

    def __init__(self):
        # identity_id -> list of asyncio.Queue (one per active SSE connection)
        self._connections: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, identity_id: str) -> asyncio.Queue:
        """Register a new SSE connection for `identity_id`. Returns its event queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        async with self._lock:
            self._connections[identity_id].append(queue)
        logger.info(f"SSE connection opened for identity={identity_id}  "
                    f"total={len(self._connections[identity_id])}")
        return queue

    async def disconnect(self, identity_id: str, queue: asyncio.Queue):
        """Remove a closed SSE connection from the registry."""
        async with self._lock:
            try:
                self._connections[identity_id].remove(queue)
            except ValueError:
                pass
            if not self._connections[identity_id]:
                del self._connections[identity_id]
        logger.info(f"SSE connection closed for identity={identity_id}")

    async def broadcast_termination(
        self,
        identity_id: str,
        reason: str,
        risk_score: float,
        triggered_by: str = "ml_engine",
    ) -> int:
        """
        Push a `session_terminated` event to all SSE streams for `identity_id`.

        Returns the number of connections notified.
        """
        event = {
            "type": "session_terminated",
            "reason": reason,
            "risk_score": risk_score,
            "triggered_by": triggered_by,
            "timestamp": time.time(),
        }
        payload = _format_sse_event("session_terminated", event)

        async with self._lock:
            queues = list(self._connections.get(identity_id, []))

        notified = 0
        for q in queues:
            try:
                q.put_nowait(payload)
                notified += 1
            except asyncio.QueueFull:
                logger.warning(f"SSE queue full for identity={identity_id}, dropping event")

        logger.info(f"SSE broadcast session_terminated  identity={identity_id}  "
                    f"reason={reason}  connections_notified={notified}")
        return notified

    async def broadcast_risk_update(self, identity_id: str, risk_score: float, tier: str):
        """Optional: push live risk score updates to connected clients."""
        event = {"type": "risk_update", "risk_score": risk_score, "tier": tier, "timestamp": time.time()}
        payload = _format_sse_event("risk_update", event)
        async with self._lock:
            queues = list(self._connections.get(identity_id, []))
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def broadcast_event(
        self,
        identity_id: str,
        event_name: str,
        data: dict,
    ) -> int:
        """
        Generic SSE broadcast to all connections for `identity_id`.
        Used for session_restricted, risk_update, and any future event types.
        Returns the number of connections notified.
        """
        data.setdefault("timestamp", time.time())
        payload = _format_sse_event(event_name, data)

        async with self._lock:
            queues = list(self._connections.get(identity_id, []))

        notified = 0
        for q in queues:
            try:
                q.put_nowait(payload)
                notified += 1
            except asyncio.QueueFull:
                logger.warning(
                    f"SSE queue full for identity={identity_id}, dropping {event_name} event"
                )

        logger.info(
            f"SSE broadcast {event_name}  identity={identity_id}  "
            f"connections_notified={notified}"
        )
        return notified

    async def event_generator(
        self,
        identity_id: str,
        queue: asyncio.Queue,
        ping_interval_s: int = 30,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator consumed by the SSE endpoint.
        Yields formatted SSE strings, including periodic keepalive pings.
        """
        try:
            while True:
                try:
                    # Wait for the next event with a timeout for keepalive pings
                    event_data = await asyncio.wait_for(queue.get(), timeout=ping_interval_s)
                    yield event_data
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent proxy timeout
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect(identity_id, queue)

    def active_connection_count(self) -> int:
        return sum(len(qs) for qs in self._connections.values())

    def connected_identities(self) -> List[str]:
        return list(self._connections.keys())


def _format_sse_event(event_type: str, data: dict) -> str:
    """Format a dict as an SSE message string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ── Singleton ──────────────────────────────────────────────────────────────────

_sse_manager: Optional[SSEManager] = None


def get_sse_manager() -> SSEManager:
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEManager()
    return _sse_manager
