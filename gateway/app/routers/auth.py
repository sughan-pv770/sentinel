"""
Authentication API Router — /api/auth/*

Endpoints:
  POST /api/auth/login   — Authenticate with identity_id + password
  POST /api/auth/logout  — Clear session cookie
  GET  /api/auth/me      — Return current user's profile
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.auth import (
    verify_password,
    create_access_token,
    get_current_user,
)
from app.state_store import get_store
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "sentinelx_token"
COOKIE_MAX_AGE = settings.jwt_expire_minutes * 60  # seconds


class LoginRequest(BaseModel):
    identity_id: str
    password: str


@router.post("/login")
async def login(req: LoginRequest, response: Response):
    """
    Authenticate user and set a signed httpOnly JWT cookie.
    Demo credentials:
      - u_admin / admin123
      - u_alex  / student123
      - u_mina  / student123
      - u_manager1 / manager123
    """
    store = get_store()
    users = await store.list_users()
    user = next((u for u in users if u["identity_id"] == req.identity_id), None)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    stored_hash = user.get("password_hash", "")
    # Allow demo fallback: if no hash stored, use role-based default passwords
    if not stored_hash:
        demo_passwords = {
            "admin":   "admin123",
            "manager": "manager123",
            "student": "student123",
            "service": "service123",
        }
        expected = demo_passwords.get(user.get("role", "student"), "student123")
        if req.password != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
    else:
        if not verify_password(req.password, stored_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

    token = create_access_token({"sub": user["identity_id"], "role": user["role"]})

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=COOKIE_MAX_AGE,
        samesite="lax",
        secure=False,  # Set True in production with HTTPS
    )

    return {
        "status": "ok",
        "identity_id": user["identity_id"],
        "name": user.get("name", user["identity_id"]),
        "role": user["role"],
        "network_tag": user.get("network_tag"),
    }


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME)
    return {"status": "logged_out"}


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
