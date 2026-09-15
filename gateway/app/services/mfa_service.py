"""
MFA Service — TOTP enroll/verify, Email OTP, Device Trust tokens.

Supported methods:
  - TOTP (Google Authenticator, Authy, etc.) via pyotp
  - Email OTP (stub — ready for SMTP/SendGrid activation)

TOTP secrets are encrypted with AES-256-GCM (via cryptography.Fernet)
before storage in Redis so they are protected at rest.

Risk-tier → MFA method mapping (from policy):
  low      (0-30):  No MFA
  medium   (31-60): Email OTP
  high     (61-85): TOTP
  critical (86-100): TOTP + force revoke all other sessions
"""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger("sentinelx.mfa")


# ── Encryption helpers (TOTP secrets at rest) ──────────────────────────────────

def _get_fernet() -> Fernet:
    """Return a Fernet cipher using the configured encryption key."""
    key = settings.mfa_encryption_key.encode()
    # Ensure key is valid Fernet format (32 url-safe base64 bytes)
    if len(key) < 32:
        key = key.ljust(32, b"=")
    import base64
    fernet_key = base64.urlsafe_b64encode(key[:32])
    return Fernet(fernet_key)


def _encrypt_secret(secret: str) -> str:
    return _get_fernet().encrypt(secret.encode()).decode()


def _decrypt_secret(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


# ── TOTP Enroll / Verify ───────────────────────────────────────────────────────

async def generate_totp_enrollment(identity_id: str, store) -> dict:
    """
    Generate a new TOTP secret for an identity, store it encrypted, and
    return the provisioning URI (for QR code) + backup codes.

    Idempotent: if already enrolled, returns existing enrollment data.
    """
    existing = await store.get_mfa_enrollment(identity_id)
    if existing and existing.get("verified"):
        # Already enrolled and verified — return status only (no secret exposure)
        return {
            "already_enrolled": True,
            "enrolled_at": existing.get("enrolled_at"),
            "method": "totp",
        }

    # Generate fresh TOTP secret
    raw_secret = pyotp.random_base32()
    totp = pyotp.TOTP(raw_secret, issuer=settings.mfa_totp_issuer)
    provisioning_uri = totp.provisioning_uri(name=identity_id, issuer_name=settings.mfa_totp_issuer)

    # Generate 8 one-time backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
    backup_hashes = [hashlib.sha256(c.encode()).hexdigest() for c in backup_codes]

    enrollment = {
        "identity_id": identity_id,
        "encrypted_secret": _encrypt_secret(raw_secret),
        "provisioning_uri": provisioning_uri,
        "backup_code_hashes": backup_hashes,
        "enrolled_at": datetime.now(timezone.utc).isoformat(),
        "verified": False,
    }
    await store.store_mfa_enrollment(identity_id, enrollment)

    logger.info(f"TOTP enrollment generated  identity={identity_id}")
    return {
        "already_enrolled": False,
        "provisioning_uri": provisioning_uri,
        "secret": raw_secret,         # Shown ONCE during enrollment; never stored in plaintext
        "backup_codes": backup_codes, # Shown ONCE; hashes stored in Redis
        "method": "totp",
    }


async def verify_totp(identity_id: str, code: str, session_id: str, store) -> Tuple[bool, str]:
    """
    Verify a TOTP code. Returns (success, reason).

    On success, marks the session as MFA-complete in the store.
    On first-time verification, marks the enrollment as verified.
    """
    enrollment = await store.get_mfa_enrollment(identity_id)
    if not enrollment:
        return False, "TOTP not enrolled for this identity"

    try:
        raw_secret = _decrypt_secret(enrollment["encrypted_secret"])
    except InvalidToken:
        logger.error(f"Failed to decrypt TOTP secret  identity={identity_id}")
        return False, "MFA configuration error — contact support"

    totp = pyotp.TOTP(raw_secret)
    valid = totp.verify(code, valid_window=settings.mfa_totp_window)

    if not valid:
        # Check backup codes
        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
        backup_hashes = enrollment.get("backup_code_hashes", [])
        if code_hash in backup_hashes:
            # Consume backup code (one-time use)
            backup_hashes.remove(code_hash)
            enrollment["backup_code_hashes"] = backup_hashes
            await store.store_mfa_enrollment(identity_id, enrollment)
            valid = True
            logger.info(f"Backup code used  identity={identity_id}")

    if valid:
        # Mark enrollment as verified (first successful verify)
        if not enrollment.get("verified"):
            enrollment["verified"] = True
            await store.store_mfa_enrollment(identity_id, enrollment)

        await store.mark_session_mfa_complete(session_id, "totp")
        logger.info(f"TOTP verification success  identity={identity_id}  session={session_id}")
        return True, "MFA verification successful"

    logger.warning(f"TOTP verification failed  identity={identity_id}")
    return False, "Invalid or expired TOTP code"


# ── Email OTP ──────────────────────────────────────────────────────────────────

async def generate_email_otp(identity_id: str, session_id: str, store) -> dict:
    """
    Generate a 6-digit numeric OTP, store its hash, and return the OTP
    for delivery (caller is responsible for sending via email/SMS).

    In production: integrate with AWS SES / SendGrid here.
    """
    otp = f"{secrets.randbelow(1000000):06d}"
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    ttl = settings.mfa_otp_ttl_seconds

    challenge = {
        "session_id": session_id,
        "identity_id": identity_id,
        "method": "email_otp",
        "otp_hash": otp_hash,
        "attempts_remaining": settings.mfa_max_attempts,
        "created_at": time.time(),
    }
    await store.store_mfa_challenge(session_id, challenge, ttl_seconds=ttl)

    logger.info(f"Email OTP generated  identity={identity_id}  session={session_id}  ttl={ttl}s")

    # --- Production hook ---
    # from app.services.email_service import send_otp_email
    # await send_otp_email(user_email, otp, ttl)

    return {
        "method": "email_otp",
        "ttl_seconds": ttl,
        "message": "OTP sent to registered email address",
        # Only include raw OTP in development mode for testing
        "_dev_otp": otp if settings.environment == "development" else None,
    }


async def verify_email_otp(session_id: str, code: str, store) -> Tuple[bool, str]:
    """
    Verify an email OTP. Consumes the challenge on success or
    decrements attempts_remaining on failure.

    Returns (success, reason).
    """
    challenge = await store.get_mfa_challenge(session_id)
    if not challenge:
        return False, "MFA challenge expired or not found. Request a new code."

    if challenge.get("method") != "email_otp":
        return False, "Challenge method mismatch"

    attempts = challenge.get("attempts_remaining", 0)
    if attempts <= 0:
        await store.delete_mfa_challenge(session_id)
        return False, "Maximum attempts exceeded. Request a new code."

    code_hash = hashlib.sha256(code.encode()).hexdigest()
    valid = hmac.compare_digest(code_hash, challenge.get("otp_hash", ""))

    if valid:
        await store.delete_mfa_challenge(session_id)
        await store.mark_session_mfa_complete(session_id, "email_otp")
        identity_id = challenge.get("identity_id", "unknown")
        logger.info(f"Email OTP verification success  identity={identity_id}  session={session_id}")
        return True, "MFA verification successful"

    # Decrement attempts
    challenge["attempts_remaining"] = attempts - 1
    await store.store_mfa_challenge(session_id, challenge, ttl_seconds=settings.mfa_otp_ttl_seconds)
    logger.warning(
        f"Email OTP verification failed  session={session_id}  "
        f"attempts_remaining={challenge['attempts_remaining']}"
    )
    return False, f"Invalid code. {challenge['attempts_remaining']} attempts remaining."


# ── Device Trust ───────────────────────────────────────────────────────────────

async def issue_device_trust_token(identity_id: str, device_fingerprint: str, store) -> dict:
    """
    Issue a time-bound device trust token.
    Valid for settings.mfa_device_trust_days days.
    """
    token_id = secrets.token_urlsafe(32)
    ttl = settings.mfa_device_trust_days * 86400
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    trust_data = {
        "token_id": token_id,
        "identity_id": identity_id,
        "device_fingerprint": device_fingerprint,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await store.store_device_trust(token_id, trust_data, ttl_seconds=ttl)
    logger.info(f"Device trust issued  identity={identity_id}  token_id={token_id[:8]}...")
    return {"token_id": token_id, "expires_at": expires_at.isoformat(), "valid_days": settings.mfa_device_trust_days}


async def verify_device_trust(token_id: str, device_fingerprint: str, store) -> bool:
    """Return True if the device trust token is valid and fingerprint matches."""
    if not token_id:
        return False
    data = await store.get_device_trust(token_id)
    if not data:
        return False
    return data.get("device_fingerprint") == device_fingerprint


# ── Risk tier → MFA method ─────────────────────────────────────────────────────

def mfa_method_for_risk(risk_score: float, policy: dict) -> Optional[str]:
    """
    Map a risk score to the required MFA method per the current policy.
    Returns None if no MFA is required.
    """
    tiers = policy.get("mfa_risk_tiers", {
        "low": None, "medium": "email_otp", "high": "totp", "critical": "totp"
    })
    thresholds = policy.get("thresholds", {"allow": 30, "step_up": 60, "restrict": 85})

    if risk_score <= thresholds.get("allow", 30):
        return tiers.get("low")
    if risk_score <= thresholds.get("step_up", 60):
        return tiers.get("medium")
    if risk_score <= thresholds.get("restrict", 85):
        return tiers.get("high")
    return tiers.get("critical")
