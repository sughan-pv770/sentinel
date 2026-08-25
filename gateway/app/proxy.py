"""
Forwards a request to the real origin microservice (§3 step 7: "request
forwarded unchanged"). Used only when the decision engine's tier is
"allow" (or, for step-up, after the mocked challenge is satisfied).
"""
from __future__ import annotations
import httpx
from fastapi import Request
from app.config import settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=settings.origin_base_url, timeout=5.0)
    return _client


async def forward(request: Request, path: str, identity_id: str) -> httpx.Response:
    client = get_client()
    body = await request.body()
    headers = dict(request.headers)
    headers["x-identity-id"] = identity_id
    headers.pop("host", None)
    headers.pop("content-length", None)

    resp = await client.request(
        method=request.method,
        url=f"/{path}",
        content=body if body else None,
        headers=headers,
        params=dict(request.query_params),
    )
    return resp
