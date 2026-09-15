"""
Authentication API Router — /api/auth/*

Endpoints:
  POST /api/auth/login        — Authenticate, issue access + refresh tokens
  POST /api/auth/refresh      — Rotate access token using refresh token
  POST /api/auth/logout       — Revoke current session, clear cookies
  POST /api/auth/revoke-all   — (Admin) Revoke all sessions for an identity
  GET  /api/auth/me           — Return current user profile
"""
from __future__ import annotations
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from jose import JWTError
from pydantic import BaseModel
from typing import Optional

from app.auth import (
    verify_password,
    create_access_token,
    get_current_user,
    require_role,
    decode_refresh_token,
    create_refresh_token,
    extract_jti,
)
from app.state_store import get_store
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

ACCESS_COOKIE = "sentinelx_token"
REFRESH_COOKIE = "sentinelx_refresh"
ACCESS_MAX_AGE = settings.jwt_expire_minutes * 60
REFRESH_MAX_AGE = settings.jwt_refresh_expire_hours * 3600


class LoginRequest(BaseModel):
    identity_id: str
    password: str


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    """
    Authenticate user and set signed httpOnly JWT cookies.
    Issues both an access token (short-lived) and a refresh token (7 days).

    Demo credentials:
      - u_admin    / admin123
      - u_alex     / student123
      - u_mina     / student123
      - u_manager1 / manager123
    """
    from app.services.rate_limiter import check_ip_rate, RateLimitExceeded
    store = get_store()
    client_ip = request.client.host if request.client else "0.0.0.0"

    # Per-IP brute-force protection on login
    try:
        await check_ip_rate(client_ip, store, window_seconds=60, limit=20)
    except RateLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait before trying again.",
        )

    users = await store.list_users()
    user = next((u for u in users if u["identity_id"] == req.identity_id), None)

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    stored_hash = user.get("password_hash", "")
    if not stored_hash:
        demo_passwords = {
            "admin": "admin123", "manager": "manager123",
            "student": "student123", "service": "service123",
        }
        expected = demo_passwords.get(user.get("role", "student"), "student123")
        if req.password != expected:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    else:
        if not verify_password(req.password, stored_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Issue tokens via session service
    from app.services.session_service import create_session
    session_data = await create_session(user["identity_id"], user["role"], store)

    # Check MFA enrollment status
    enrollment = await store.get_mfa_enrollment(user["identity_id"])
    mfa_enrolled = bool(enrollment and enrollment.get("verified"))

    _set_auth_cookies(response, session_data["access_token"], session_data["refresh_token"])

    return {
        "status": "ok",
        "identity_id": user["identity_id"],
        "name": user.get("name", user["identity_id"]),
        "role": user["role"],
        "network_tag": user.get("network_tag"),
        "session_id": session_data["session_id"],
        "mfa_enrolled": mfa_enrolled,
    }


# ── Refresh ────────────────────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh(
    response: Response,
    sentinelx_refresh: Optional[str] = Cookie(default=None),
):
    """
    Issue a new access token using a valid refresh token.
    Rotates the refresh token (issues a new one, revokes the old JTI).
    """
    if not sentinelx_refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    try:
        payload = decode_refresh_token(sentinelx_refresh)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    identity_id = payload.get("sub")
    old_refresh_jti = payload.get("jti")
    store = get_store()

    # Revoke old refresh JTI (token rotation — prevents replay)
    if old_refresh_jti:
        await store.revoke_jti(old_refresh_jti, ttl_seconds=settings.jwt_refresh_expire_hours * 3600 + 60)

    users = await store.list_users()
    user = next((u for u in users if u["identity_id"] == identity_id), None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    from app.services.session_service import create_session
    session_data = await create_session(identity_id, user["role"], store)

    _set_auth_cookies(response, session_data["access_token"], session_data["refresh_token"])
    return {"status": "ok", "session_id": session_data["session_id"]}


# ── Logout ─────────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(
    response: Response,
    current_user: dict = Depends(get_current_user),
    sentinelx_token: Optional[str] = Cookie(default=None),
    sentinelx_refresh: Optional[str] = Cookie(default=None),
):
    """Revoke the current session tokens and clear cookies."""
    store = get_store()

    jti = current_user.get("_jti")
    if jti:
        await store.revoke_jti(jti, ttl_seconds=ACCESS_MAX_AGE + 60)

    # Revoke refresh token JTI if present
    if sentinelx_refresh:
        try:
            refresh_payload = decode_refresh_token(sentinelx_refresh)
            refresh_jti = refresh_payload.get("jti")
            if refresh_jti:
                await store.revoke_jti(refresh_jti, ttl_seconds=REFRESH_MAX_AGE + 60)
        except JWTError:
            pass

    _clear_auth_cookies(response)
    return {"status": "logged_out"}


# ── Revoke All (Admin) ─────────────────────────────────────────────────────────

@router.post("/revoke-all/{identity_id}")
async def revoke_all(
    identity_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Admin: immediately revoke all sessions for an identity and broadcast SSE."""
    store = get_store()
    from app.services.session_service import revoke_all_sessions_and_broadcast
    result = await revoke_all_sessions_and_broadcast(
        identity_id=identity_id,
        reason="admin_forced_revocation",
        risk_score=100.0,
        triggered_by="admin_manual",
        store=store,
    )
    return {"status": "revoked", **result}


# ── Me ─────────────────────────────────────────────────────────────────────────

@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return {
        "identity_id": current_user["identity_id"],
        "name": current_user.get("name", current_user["identity_id"]),
        "role": current_user["role"],
        "network_tag": current_user.get("network_tag"),
        "supervisor_id": current_user.get("supervisor_id"),
    }


# ── Cookie helpers ─────────────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    is_prod = settings.environment == "production"
    response.set_cookie(
        key=ACCESS_COOKIE, value=access_token, httponly=True,
        max_age=ACCESS_MAX_AGE, samesite="lax", secure=is_prod,
    )
    response.set_cookie(
        key=REFRESH_COOKIE, value=refresh_token, httponly=True,
        max_age=REFRESH_MAX_AGE, samesite="lax", secure=is_prod,
        path="/api/auth/refresh",  # Scoped to refresh endpoint only
    )


def _clear_auth_cookies(response: Response):
    response.delete_cookie(key=ACCESS_COOKIE)
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/auth/refresh")
