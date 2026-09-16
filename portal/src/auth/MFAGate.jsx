/**
 * MFAGate — Global MFA interceptor.
 *
 * Shows the TOTP/OTP modal in two ways:
 *  1. Via secureCall(fn) — wraps any API call; if it throws step_up_required
 *     the modal appears and retries the request on success.
 *  2. Via SSE — when the gateway broadcasts an mfa_challenge event (e.g. from
 *     the simulator), AuthContext sets pendingMfaChallenge which triggers the
 *     modal immediately without waiting for the next API call.
 */
import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { mfa as mfaApi, retryPendingRequest } from '../api/client';
import { useAuth } from './AuthContext';
import { Lock, KeyRound, Clock, X } from 'lucide-react';

const MFAGateContext = createContext(null);

export function MFAGateProvider({ children }) {
  const { logout, pendingMfaChallenge, clearMfaChallenge } = useAuth();

  // State for the modal — either from secureCall or SSE push
  const [mfaState, setMfaState] = useState(null);
  // { challenge, pendingError? }  pendingError is set only from secureCall
  const resolveRef = useRef(null);
  const rejectRef  = useRef(null);

  // ── Watch for SSE-pushed mfa_challenge (from simulator step_up) ───────────
  useEffect(() => {
    if (pendingMfaChallenge && !mfaState) {
      setMfaState({ challenge: pendingMfaChallenge, pendingError: null });
    }
  }, [pendingMfaChallenge]); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * secureCall — wraps any API fn.
   * If it returns step_up_required, shows the MFA modal and retries on success.
   */
  const secureCall = useCallback(async (fn) => {
    try {
      return await fn();
    } catch (err) {
      if (err.mfaRequired) {
        return new Promise((resolve, reject) => {
          resolveRef.current = resolve;
          rejectRef.current  = reject;
          setMfaState({ challenge: err.challenge, pendingError: err });
        });
      }
      throw err;
    }
  }, []);

  const handleVerified = useCallback(async (pendingError) => {
    setMfaState(null);
    clearMfaChallenge();
    if (pendingError) {
      // Retry the original blocked request
      try {
        const result = await retryPendingRequest(pendingError);
        resolveRef.current?.(result);
      } catch (err) {
        rejectRef.current?.(err);
      }
    } else {
      // SSE-triggered modal — no pending request to retry, just close
      resolveRef.current?.(null);
    }
  }, [clearMfaChallenge]);

  const handleCancel = useCallback(async () => {
    setMfaState(null);
    clearMfaChallenge();
    rejectRef.current?.(new Error('MFA cancelled'));
    await logout();
  }, [logout, clearMfaChallenge]);

  return (
    <MFAGateContext.Provider value={{ secureCall }}>
      {children}
      {mfaState && (
        <MFAModal
          challenge={mfaState.challenge}
          pendingError={mfaState.pendingError}
          onVerified={handleVerified}
          onCancel={handleCancel}
        />
      )}
    </MFAGateContext.Provider>
  );
}

export function useMFAGate() {
  const ctx = useContext(MFAGateContext);
  if (!ctx) throw new Error('useMFAGate must be used within MFAGateProvider');
  return ctx;
}

// ── TOTP / OTP Modal ──────────────────────────────────────────────────────────

function MFAModal({ challenge, pendingError, onVerified, onCancel }) {
  const [code, setCode]       = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');
  const ttl = challenge?.ttl_seconds || 300;
  const [timeLeft, setTimeLeft] = useState(ttl);

  const method    = challenge?.method || 'totp';
  const sessionId = challenge?.session_id
    || pendingError?.data?.challenge?.session_id
    || '';

  // Countdown
  useEffect(() => {
    if (timeLeft <= 0) return;
    const t = setInterval(() => setTimeLeft(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  const fmt = s => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const handleSubmit = async (e) => {
    e.preventDefault();
    const clean = code.replace(/\s/g, '');
    if (clean.length < 6) { setError('Enter a 6-digit code'); return; }
    setError('');
    setLoading(true);
    try {
      if (method === 'totp') {
        await mfaApi.verifyTotp(clean, sessionId, false);
      } else {
        await mfaApi.verifyOtp(clean, sessionId);
      }
      await onVerified(pendingError);
    } catch (err) {
      setError(err?.data?.detail || 'Invalid code — please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.78)',
      backdropFilter: 'blur(12px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16,
      animation: 'fadeIn 0.2s ease',
    }}>
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 18, padding: 32,
        width: '100%', maxWidth: 420,
        boxShadow: '0 30px 70px rgba(0,0,0,0.55)',
        position: 'relative',
      }}>
        {/* Close */}
        <button onClick={onCancel} style={{
          position: 'absolute', top: 16, right: 16,
          background: 'transparent', border: 'none',
          color: 'var(--text-muted)', cursor: 'pointer',
        }}>
          <X size={18} />
        </button>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <div style={{
            width: 50, height: 50, borderRadius: 14,
            background: 'linear-gradient(135deg, #f59e0b, #d97706)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Lock size={22} color="white" strokeWidth={1.5} />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
              Security Verification Required
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
              Unusual activity detected — verify your identity
            </div>
          </div>
        </div>

        {/* Method pill */}
        <div style={{
          background: 'rgba(59,130,246,0.1)',
          border: '1px solid rgba(59,130,246,0.2)',
          borderRadius: 10, padding: '10px 14px',
          display: 'flex', alignItems: 'center', gap: 8,
          marginBottom: 20,
        }}>
          <KeyRound size={15} color="#3b82f6" />
          <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
            {method === 'totp'
              ? 'Open your Authenticator App and enter the 6-digit code'
              : 'Enter the 6-digit code sent to your email'}
          </span>
        </div>

        {/* Countdown */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          color: timeLeft <= 30 ? '#ef4444' : 'var(--text-muted)',
          fontSize: 12, marginBottom: 16,
        }}>
          <Clock size={13} />
          {timeLeft > 0 ? `Code expires in ${fmt(timeLeft)}` : 'Code expired — close and retry'}
        </div>

        <form onSubmit={handleSubmit}>
          <input
            autoFocus
            className="input"
            type="text"
            inputMode="numeric"
            maxLength={8}
            value={code}
            onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
            placeholder="000000"
            disabled={timeLeft <= 0}
            style={{
              textAlign: 'center',
              fontSize: 30,
              letterSpacing: '0.45em',
              fontFamily: 'monospace',
              padding: '14px',
              marginBottom: 12,
            }}
          />

          {error && (
            <div style={{
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 8, padding: '10px 12px',
              color: '#ef4444', fontSize: 13, marginBottom: 12,
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || timeLeft <= 0}
            style={{ width: '100%', justifyContent: 'center', padding: 13, fontSize: 14 }}
          >
            {loading ? 'Verifying…' : '✓ Verify & Continue'}
          </button>

          <button
            type="button"
            onClick={onCancel}
            style={{
              width: '100%', marginTop: 10, padding: 10,
              background: 'transparent',
              border: '1px solid var(--border)',
              borderRadius: 8, color: 'var(--text-muted)',
              cursor: 'pointer', fontSize: 13,
            }}
          >
            Cancel — Sign Out
          </button>
        </form>
      </div>
    </div>
  );
}
