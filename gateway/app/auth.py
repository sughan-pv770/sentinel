"""
Authentication utilities for SentinelX Portal.

Provides:
- JWT access token creation and verification (with JTI for revocation)
- Refresh token creation and verification (separate secret)
- Password hashing with bcrypt
- FastAPI dependency functions for route protection
- Role-based access control helpers
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import uuid

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password Helpers ────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT Access Token ────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed access token. The payload MUST include 'sub' (identity_id).
    A unique 'jti' (JWT ID) is added if not already present, enabling
    individual token revocation without invalidating all user sessions.
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload["exp"] = expire
    if "jti" not in payload:
        payload["jti"] = str(uuid.uuid4())
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def extract_jti(token: str) -> Optional[str]:
    """Extract JTI from a token without full validation (for blacklist lookup)."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        return payload.get("jti")
    except JWTError:
        return None


# ── JWT Refresh Token ───────────────────────────────────────────────────────────

def create_refresh_token(identity_id: str, access_jti: str) -> str:
    """
    Create a long-lived refresh token signed with a separate secret.
    Links to the access token JTI so the token family can be tracked.
    """
    payload = {
        "sub": identity_id,
        "jti": str(uuid.uuid4()),
        "access_jti": access_jti,  # links refresh ↔ access for family tracking
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_refresh_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_refresh_secret_key, algorithm=settings.jwt_algorithm)


def decode_refresh_token(token: str) -> dict:
    payload = jwt.decode(
        token, settings.jwt_refresh_secret_key, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "refresh":
        raise JWTError("Not a refresh token")
    return payload


# ── FastAPI Dependencies ────────────────────────────────────────────────────────

async def get_current_user(
    sentinelx_token: Optional[str] = Cookie(default=None),
) -> dict:
    """
    Extracts and validates the JWT from the httpOnly cookie.
    Checks JTI against the revocation blacklist.
    Returns the user dict (identity_id, name, role, etc.).
    Raises 401 if token is missing, invalid, or revoked.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not sentinelx_token:
        raise credentials_exception
    try:
        payload = decode_token(sentinelx_token)
        identity_id: str = payload.get("sub")
        jti: str = payload.get("jti")
        if identity_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    from app.state_store import get_store
    store = get_store()

    # JTI revocation check
    if jti and await store.is_jti_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session_terminated",
            headers={"X-SentinelX-Reason": "token_revoked"},
        )

    users = await store.list_users()
    user = next((u for u in users if u["identity_id"] == identity_id), None)
    if user is None:
        raise credentials_exception
    return {**user, "_jti": jti, "_session_id": payload.get("session_id")}


def require_role(*roles: str):
    """
    Dependency factory that enforces role-based access.
    Usage: Depends(require_role("admin"))  or  Depends(require_role("admin", "manager"))
    """
    async def _check(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {list(roles)}",
            )
        return current_user
    return _check
