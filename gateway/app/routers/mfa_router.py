"""
MFA Router — /api/mfa/*

Endpoints:
  POST /api/mfa/enroll/totp        — Generate TOTP secret + QR provisioning URI
  POST /api/mfa/verify/totp        — Verify TOTP code, mark session MFA-complete
  POST /api/mfa/enroll/email-otp   — Send email OTP for current session
  POST /api/mfa/verify/otp         — Verify email/SMS OTP code
  GET  /api/mfa/status             — MFA enrollment + session status
  POST /api/mfa/trust-device       — Issue 30-day device trust token
  DELETE /api/mfa/trust-device     — Revoke device trust
"""
from __future__ import annotations
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional

from app.auth import get_current_user
from app.state_store import get_store
from app.services import mfa_service

router = APIRouter(prefix="/api/mfa", tags=["mfa"])


class TOTPVerifyRequest(BaseModel):
    code: str
    session_id: str
    trust_device: bool = False


class OTPVerifyRequest(BaseModel):
    code: str
    session_id: str


class DeviceTrustRequest(BaseModel):
    token_id: str


# ── TOTP Enrollment ────────────────────────────────────────────────────────────

@router.post("/enroll/totp")
async def enroll_totp(current_user: dict = Depends(get_current_user)):
    """
    Generate a TOTP secret and provisioning URI for the authenticated user.
    Returns a base64 QR PNG so frontend can display with <img src=...>.
    The secret and backup_codes are shown ONCE — not retrievable again.
    """
    store = get_store()
    result = await mfa_service.generate_totp_enrollment(
        identity_id=current_user["identity_id"],
        store=store,
    )
    # Embed QR code PNG as base64 for direct <img> rendering
    if not result.get("already_enrolled") and result.get("provisioning_uri"):
        try:
            import qrcode
            import io
            import base64
            qr = qrcode.QRCode(
                box_size=6, border=2,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
            )
            qr.add_data(result["provisioning_uri"])
            qr.make(fit=True)
            img = qr.make_image(fill_color="#1a1a2e", back_color="#ffffff")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            result["qr_code_png"] = (
                "data:image/png;base64,"
                + base64.b64encode(buf.getvalue()).decode()
            )
        except Exception:
            pass  # frontend falls back to showing manual secret entry
    return result


@router.post("/verify/totp")
async def verify_totp(
    req: TOTPVerifyRequest,
    current_user: dict = Depends(get_current_user),
    request: Request = None,
):
    """
    Verify a 6-digit TOTP code (or 8-character backup code).
    On success, marks the session as MFA-complete.
    """
    store = get_store()
    success, message = await mfa_service.verify_totp(
        identity_id=current_user["identity_id"],
        code=req.code,
        session_id=req.session_id,
        store=store,
    )

    if not success:
        from app.observability import mfa_verifications_total
        mfa_verifications_total.labels(method="totp", result="failure").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    from app.observability import mfa_verifications_total
    mfa_verifications_total.labels(method="totp", result="success").inc()

    result = {"status": "verified", "message": message, "method": "totp"}

    # Optionally issue a device trust token
    if req.trust_device:
        device_fp = _device_fingerprint(request)
        trust = await mfa_service.issue_device_trust_token(
            identity_id=current_user["identity_id"],
            device_fingerprint=device_fp,
            store=store,
        )
        result["device_trust"] = trust

    return result


# ── Email OTP ──────────────────────────────────────────────────────────────────

@router.post("/enroll/email-otp")
async def enroll_email_otp(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate and send an email OTP for the current session."""
    store = get_store()
    result = await mfa_service.generate_email_otp(
        identity_id=current_user["identity_id"],
        session_id=session_id,
        store=store,
    )
    return result


@router.post("/verify/otp")
async def verify_otp(
    req: OTPVerifyRequest,
    current_user: dict = Depends(get_current_user),
):
    """Verify an email/SMS OTP code for the current session."""
    store = get_store()
    success, message = await mfa_service.verify_email_otp(
        session_id=req.session_id,
        code=req.code,
        store=store,
    )

    if not success:
        from app.observability import mfa_verifications_total
        mfa_verifications_total.labels(method="email_otp", result="failure").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    from app.observability import mfa_verifications_total
    mfa_verifications_total.labels(method="email_otp", result="success").inc()
    return {"status": "verified", "message": message, "method": "email_otp"}


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def mfa_status(
    session_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Return MFA enrollment and session completion status."""
    store = get_store()
    identity_id = current_user["identity_id"]

    enrollment = await store.get_mfa_enrollment(identity_id)
    mfa_complete = False
    if session_id:
        mfa_complete = await store.is_session_mfa_complete(session_id)

    return {
        "identity_id": identity_id,
        "totp_enrolled": bool(enrollment and enrollment.get("verified")),
        "enrollment_date": enrollment.get("enrolled_at") if enrollment else None,
        "backup_codes_remaining": len(enrollment.get("backup_code_hashes", [])) if enrollment else 0,
        "session_mfa_complete": mfa_complete,
    }


# ── Device Trust ───────────────────────────────────────────────────────────────

@router.post("/trust-device")
async def trust_device(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Issue a 30-day device trust token for the current device."""
    store = get_store()
    device_fp = _device_fingerprint(request)
    result = await mfa_service.issue_device_trust_token(
        identity_id=current_user["identity_id"],
        device_fingerprint=device_fp,
        store=store,
    )
    return result


@router.delete("/trust-device")
async def revoke_trust_device(
    req: DeviceTrustRequest,
    current_user: dict = Depends(get_current_user),
):
    """Revoke a device trust token."""
    store = get_store()
    await store.revoke_device_trust(req.token_id)
    return {"status": "revoked", "token_id": req.token_id}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _device_fingerprint(request: Request) -> str:
    """Simple device fingerprint: hash of IP + User-Agent."""
    import hashlib
    ip = request.client.host if request.client else "0.0.0.0"
    ua = request.headers.get("user-agent", "unknown")
    return hashlib.sha256(f"{ip}:{ua}".encode()).hexdigest()[:32]
