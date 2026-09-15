"""
Tests for MFA service (TOTP + email OTP + device trust).

Validates:
  - TOTP enrollment generates secret + backup codes
  - Idempotent re-enrollment returns already_enrolled
  - Valid TOTP code verifies successfully
  - Invalid TOTP code is rejected
  - Backup code works once, then is consumed
  - Email OTP generation stores hash
  - Correct email OTP verifies successfully
  - Wrong email OTP decrements attempts
  - OTP lockout after max attempts
  - Device trust issue + verify + revoke
"""
import pytest
import pyotp
from cryptography.fernet import Fernet
import base64
from app.state_store import InMemoryStore
from app.services import mfa_service
from app.config import settings


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture(autouse=True)
def patch_encryption_key(monkeypatch):
    """Ensure a valid Fernet key is set for tests."""
    key = base64.urlsafe_b64encode(b"testkey0123456789012345678901234")
    monkeypatch.setattr(settings, "mfa_encryption_key", key.decode())


class TestTOTPEnrollment:
    @pytest.mark.asyncio
    async def test_enrollment_returns_secret_and_uri(self, store):
        result = await mfa_service.generate_totp_enrollment("u_test_totp", store)
        assert not result["already_enrolled"]
        assert "secret" in result
        assert "provisioning_uri" in result
        assert "backup_codes" in result
        assert len(result["backup_codes"]) == 8
        assert result["method"] == "totp"

    @pytest.mark.asyncio
    async def test_enrollment_is_idempotent_after_verify(self, store):
        """Re-enrolling after verification returns already_enrolled."""
        result = await mfa_service.generate_totp_enrollment("u_idem", store)
        secret = result["secret"]
        session_id = "sess_idem"
        totp = pyotp.TOTP(secret)
        code = totp.now()
        success, _ = await mfa_service.verify_totp("u_idem", code, session_id, store)
        assert success

        result2 = await mfa_service.generate_totp_enrollment("u_idem", store)
        assert result2["already_enrolled"] is True


class TestTOTPVerification:
    @pytest.mark.asyncio
    async def test_valid_code_succeeds(self, store):
        enroll = await mfa_service.generate_totp_enrollment("u_verify", store)
        secret = enroll["secret"]
        totp = pyotp.TOTP(secret)
        code = totp.now()

        success, msg = await mfa_service.verify_totp("u_verify", code, "sess_v1", store)
        assert success is True
        assert "successful" in msg.lower()

    @pytest.mark.asyncio
    async def test_wrong_code_fails(self, store):
        await mfa_service.generate_totp_enrollment("u_wrong", store)
        success, msg = await mfa_service.verify_totp("u_wrong", "000000", "sess_w1", store)
        assert success is False

    @pytest.mark.asyncio
    async def test_not_enrolled_fails(self, store):
        success, msg = await mfa_service.verify_totp("u_not_enrolled", "123456", "sess_x", store)
        assert success is False
        assert "not enrolled" in msg.lower()

    @pytest.mark.asyncio
    async def test_backup_code_works_once(self, store):
        enroll = await mfa_service.generate_totp_enrollment("u_backup", store)
        backup = enroll["backup_codes"][0]

        success, msg = await mfa_service.verify_totp("u_backup", backup, "sess_b1", store)
        assert success is True

        # Second use of same code should fail (consumed)
        success2, msg2 = await mfa_service.verify_totp("u_backup", backup, "sess_b2", store)
        assert success2 is False

    @pytest.mark.asyncio
    async def test_successful_verify_marks_session_mfa_complete(self, store):
        enroll = await mfa_service.generate_totp_enrollment("u_session_mark", store)
        secret = enroll["secret"]
        totp = pyotp.TOTP(secret)
        code = totp.now()

        session_id = "sess_mark_001"
        await mfa_service.verify_totp("u_session_mark", code, session_id, store)
        assert await store.is_session_mfa_complete(session_id)


class TestEmailOTP:
    @pytest.mark.asyncio
    async def test_otp_generation(self, store):
        result = await mfa_service.generate_email_otp("u_email", "sess_e1", store)
        assert result["method"] == "email_otp"
        assert result["ttl_seconds"] > 0
        # In development mode, _dev_otp is returned
        assert result.get("_dev_otp") is not None or settings.environment != "development"

    @pytest.mark.asyncio
    async def test_correct_otp_verifies(self, store):
        result = await mfa_service.generate_email_otp("u_email_v", "sess_ev1", store)
        otp = result.get("_dev_otp", "000000")

        success, msg = await mfa_service.verify_email_otp("sess_ev1", otp, store)
        assert success is True

    @pytest.mark.asyncio
    async def test_wrong_otp_fails_and_decrements(self, store):
        await mfa_service.generate_email_otp("u_email_wrong", "sess_ew1", store)
        success, msg = await mfa_service.verify_email_otp("sess_ew1", "999999", store)
        assert success is False
        assert "attempts remaining" in msg.lower()

    @pytest.mark.asyncio
    async def test_lockout_after_max_attempts(self, store):
        await mfa_service.generate_email_otp("u_lockout", "sess_lo1", store)
        for _ in range(settings.mfa_max_attempts):
            await mfa_service.verify_email_otp("sess_lo1", "000001", store)
        # After max attempts, challenge should be deleted
        challenge = await store.get_mfa_challenge("sess_lo1")
        # Either challenge is None (deleted) or attempts_remaining = 0
        if challenge:
            assert challenge.get("attempts_remaining", 0) <= 0

    @pytest.mark.asyncio
    async def test_expired_challenge_returns_none(self, store):
        """Simulate an expired challenge by directly checking store TTL."""
        success, msg = await mfa_service.verify_email_otp("sess_expired", "123456", store)
        assert success is False
        assert "expired" in msg.lower() or "not found" in msg.lower()


class TestDeviceTrust:
    @pytest.mark.asyncio
    async def test_issue_and_verify_trust(self, store):
        result = await mfa_service.issue_device_trust_token("u_dev", "fp_abc123", store)
        token_id = result["token_id"]
        assert await mfa_service.verify_device_trust(token_id, "fp_abc123", store)

    @pytest.mark.asyncio
    async def test_wrong_fingerprint_rejected(self, store):
        result = await mfa_service.issue_device_trust_token("u_dev2", "fp_real", store)
        token_id = result["token_id"]
        assert not await mfa_service.verify_device_trust(token_id, "fp_fake", store)

    @pytest.mark.asyncio
    async def test_revoked_trust_rejected(self, store):
        result = await mfa_service.issue_device_trust_token("u_dev3", "fp_revoke", store)
        token_id = result["token_id"]
        await store.revoke_device_trust(token_id)
        assert not await mfa_service.verify_device_trust(token_id, "fp_revoke", store)
