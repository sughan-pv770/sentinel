"""
Authentication utilities for SentinelX Portal.

Provides:
- JWT token creation and verification
- Password hashing with bcrypt
- FastAPI dependency functions for route protection
- Role-based access control helpers
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Password Helpers ────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── JWT Helpers ─────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload.update({"exp": expire})
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# ─── FastAPI Dependencies ─────────────────────────────────────────────────────

async def get_current_user(
    sentinelx_token: Optional[str] = Cookie(default=None),
) -> dict:
    """
    Extracts and validates the JWT from the httpOnly cookie.
    Returns the user dict (identity_id, name, role, etc.).
    Raises 401 if token is missing or invalid.
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
        if identity_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    from app.state_store import get_store
    store = get_store()
    users = await store.list_users()
    user = next((u for u in users if u["identity_id"] == identity_id), None)
    if user is None:
        raise credentials_exception
    return user


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
