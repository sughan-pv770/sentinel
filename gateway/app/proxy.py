"""
Forwards a request to the real origin microservice (§3 step 7: "request
forwarded unchanged"). Used only when the decision engine's tier is
"allow" (or, for step-up, after the mocked challenge is satisfied).

Service lookup is now config-driven via service_registry.py — no
per-service hardcoding here.
"""
from __future__ import annotations
import httpx
from fastapi import Request
from app.service_registry import get_upstream_url

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=2.0),
            limits=httpx.Limits(
                max_connections=200,
                max_keepalive_connections=50,
                keepalive_expiry=30,
            ),
        )
    return _client


async def forward(request: Request, service: str, path: str, identity_id: str) -> httpx.Response:
    client = get_client()
    body = await request.body()
    headers = dict(request.headers)
    headers["x-identity-id"] = identity_id
    headers.pop("host", None)
    headers.pop("content-length", None)

    base_url = get_upstream_url(service)
    if not base_url:
        # Fall back gracefully — unknown services get a 502
        raise ValueError(f"Unknown service '{service}' — not registered in services.json")

    target_url = f"{base_url.rstrip('/')}/{path}"

    resp = await client.request(
        method=request.method,
        url=target_url,
        content=body if body else None,
        headers=headers,
        params=dict(request.query_params),
    )
    return resp
