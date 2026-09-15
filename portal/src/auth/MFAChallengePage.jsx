import { useState, useEffect, useRef } from 'react';
import { useAuth } from './AuthContext';
import { Shield, Lock, KeyRound, Clock } from 'lucide-react';

/**
 * MFA Challenge Page — shown when the gateway returns step_up_required.
 *
 * Supports:
 *   - TOTP code input (6-digit from authenticator app)
 *   - Email OTP input (6-digit code sent to email)
 *   - Countdown timer for OTP expiry
 *   - Trust device checkbox (30-day bypass)
 *   - Auto-retry of the original blocked request on success
 */
export default function MFAChallengePage({ challenge, onSuccess, onCancel }) {
  const { user } = useAuth();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [timeLeft, setTimeLeft] = useState(challenge?.ttl_seconds || 300);
  const [trustDevice, setTrustDevice] = useState(false);
  const inputRef = useRef(null);

  const method = challenge?.method || 'totp';
  const sessionId = challenge?.session_id || '';

  // Countdown timer
  useEffect(() => {
    if (timeLeft <= 0) return;
    const timer = setInterval(() => setTimeLeft(t => Math.max(0, t - 1)), 1000);
    return () => clearInterval(timer);
  }, [timeLeft]);

  // Auto-focus input
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (code.length < 6) {
      setError('Please enter a 6-digit code');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const { mfa } = await import('../api/client');
      let result;
      if (method === 'totp') {
        result = await mfa.verifyTotp(code, sessionId, trustDevice);
      } else {
        result = await mfa.verifyOtp(code, sessionId);
      }
      onSuccess?.(result);
    } catch (err) {
      setError(err.data?.detail || 'Verification failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const expired = timeLeft <= 0;

  return (
    <div className="login-page">
      <div className="login-card animate-fade-in" style={{ maxWidth: 420 }}>
        {/* Header */}
        <div className="login-logo">
          <div className="login-logo-icon" style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}>
            <Lock size={24} color="white" strokeWidth={1.5} />
          </div>
          <div className="login-logo-text">
            <h1 style={{ fontSize: '20px' }}>Verification Required</h1>
            <span>Additional security check</span>
          </div>
        </div>

        {/* Method description */}
        <div style={{
          background: 'rgba(59, 130, 246, 0.1)',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '10px',
          padding: '14px 16px',
          marginBottom: '20px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <KeyRound size={16} color="#3b82f6" />
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {method === 'totp' ? 'Authenticator App' : 'Email OTP'}
            </span>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5', margin: 0 }}>
            {method === 'totp'
              ? 'Enter the 6-digit code from your authenticator app (Google Authenticator, Authy, etc.)'
              : 'A 6-digit code was sent to your registered email address.'}
          </p>
        </div>

        {/* Timer */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: '6px', marginBottom: '16px',
          color: expired ? '#ef4444' : 'var(--text-muted)',
          fontSize: '13px',
        }}>
          <Clock size={14} />
          {expired ? 'Code expired — request a new one' : `Expires in ${formatTime(timeLeft)}`}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <input
              ref={inputRef}
              className="input"
              type="text"
              inputMode="numeric"
              pattern="[0-9A-Za-z]*"
              maxLength={8}
              value={code}
              onChange={e => setCode(e.target.value.replace(/\s/g, ''))}
              placeholder="000000"
              autoComplete="one-time-code"
              disabled={expired}
              style={{
                textAlign: 'center', fontSize: '24px', letterSpacing: '0.3em',
                fontFamily: 'monospace', padding: '14px',
              }}
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          {/* Trust device checkbox */}
          {method === 'totp' && (
            <label style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              fontSize: '12px', color: 'var(--text-secondary)',
              marginBottom: '16px', cursor: 'pointer',
            }}>
              <input
                type="checkbox"
                checked={trustDevice}
                onChange={e => setTrustDevice(e.target.checked)}
              />
              Trust this device for 30 days
            </label>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || expired}
            style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
          >
            {loading ? 'Verifying…' : 'Verify Code →'}
          </button>

          <button
            type="button"
            onClick={onCancel}
            style={{
              width: '100%', marginTop: '10px', padding: '10px',
              background: 'transparent', border: '1px solid var(--border)',
              borderRadius: '8px', color: 'var(--text-secondary)',
              cursor: 'pointer', fontSize: '13px',
            }}
          >
            Cancel & Sign Out
          </button>
        </form>
      </div>
    </div>
  );
}
