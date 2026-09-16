/**
 * MFAGate — Global MFA interceptor context.
 *
 * How it works:
 *  1. Any component that calls an API gets a wrapped `secureCall(fn)` helper.
 *  2. If the API throws `mfaRequired: true`, `secureCall` puts the pending call
 *     into state and opens the TOTP modal instead of letting the error bubble.
 *  3. When the user enters their TOTP code and verification succeeds, we mark
 *     the session as MFA-complete and retry the original request automatically.
 *  4. If the user cancels, the modal closes and the original error is re-thrown.
 *
 * Usage:
 *   const { secureCall } = useMFAGate();
 *   const data = await secureCall(() => api.student.overview());
 */
import {
  createContext, useContext, useState, useCallback, useRef,
} from 'react';
import { mfa as mfaApi, retryPendingRequest } from '../api/client';
import { useAuth } from './AuthContext';
import { Lock, KeyRound, Clock, ShieldAlert, X } from 'lucide-react';

const MFAGateContext = createContext(null);

export function MFAGateProvider({ children }) {
  const { logout } = useAuth();

  // The pending MFA error object (contains challenge + the pending request fn)
  const [mfaState, setMfaState] = useState(null); // { challenge, pendingFn }
  const resolveRef = useRef(null);
  const rejectRef = useRef(null);

  /**
   * secureCall — wrap any API call. If it needs MFA, shows the modal.
   * Returns the original response on success (after MFA if needed).
   */
  const secureCall = useCallback(async (fn) => {
    try {
      return await fn();
    } catch (err) {
      if (err.mfaRequired) {
        // Show modal and wait for resolution
        return new Promise((resolve, reject) => {
          resolveRef.current = resolve;
          rejectRef.current = reject;
          setMfaState({ challenge: err.challenge, pendingError: err });
        });
      }
      throw err;
    }
  }, []);

  const handleVerified = useCallback(async (pendingError) => {
    setMfaState(null);
    try {
      // Retry the original blocked request now that MFA is complete
      const result = await retryPendingRequest(pendingError);
      resolveRef.current?.(result);
    } catch (err) {
      rejectRef.current?.(err);
    }
  }, []);

  const handleCancel = useCallback(async () => {
    setMfaState(null);
    rejectRef.current?.(new Error('MFA cancelled'));
    await logout();
  }, [logout]);

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

// ── Inline TOTP Modal ─────────────────────────────────────────────────────────

function MFAModal({ challenge, pendingError, onVerified, onCancel }) {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [timeLeft, setTimeLeft] = useState(challenge?.ttl_seconds || 300);

  const method = challenge?.method || 'totp';
  const sessionId = challenge?.session_id || pendingError?.data?.challenge?.session_id || '';

  // Countdown timer
  useState(() => {
    if (timeLeft <= 0) return;
    const t = setInterval(() => setTimeLeft(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  });

  const formatTime = s => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (code.replace(/\s/g, '').length < 6) {
      setError('Enter a 6-digit code');
      return;
    }
    setError('');
    setLoading(true);
    try {
      if (method === 'totp') {
        await mfaApi.verifyTotp(code.trim(), sessionId, false);
      } else {
        await mfaApi.verifyOtp(code.trim(), sessionId);
      }
      await onVerified(pendingError);
    } catch (err) {
      setError(err.data?.detail || 'Invalid code. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    /* Full-screen dim overlay */
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.75)',
      backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16,
    }}>
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 16,
        padding: 32,
        width: '100%',
        maxWidth: 420,
        boxShadow: '0 25px 60px rgba(0,0,0,0.5)',
        position: 'relative',
      }}>
        {/* Close */}
        <button onClick={onCancel} style={{
          position: 'absolute', top: 16, right: 16,
          background: 'transparent', border: 'none',
          color: 'var(--text-muted)', cursor: 'pointer', padding: 4,
        }}>
          <X size={18} />
        </button>

        {/* Icon + title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <div style={{
            width: 48, height: 48, borderRadius: 12,
            background: 'linear-gradient(135deg, #f59e0b, #d97706)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <Lock size={22} color="white" strokeWidth={1.5} />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
              Security Verification Required
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
              Unusual activity detected — please verify your identity
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
              ? 'Enter the code from your Authenticator App'
              : 'Enter the 6-digit code sent to your email'}
          </span>
        </div>

        {/* Timer */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          color: timeLeft <= 30 ? '#ef4444' : 'var(--text-muted)',
          fontSize: 12, marginBottom: 16,
        }}>
          <Clock size={13} />
          {timeLeft > 0 ? `Expires in ${formatTime(timeLeft)}` : 'Code expired — cancel and retry'}
        </div>

        <form onSubmit={handleSubmit}>
          <input
            autoFocus
            className="input"
            type="text"
            inputMode="numeric"
            maxLength={8}
            value={code}
            onChange={e => setCode(e.target.value.replace(/\s/g, ''))}
            placeholder="000000"
            disabled={timeLeft <= 0}
            style={{
              textAlign: 'center',
              fontSize: 28,
              letterSpacing: '0.4em',
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
              color: '#ef4444', fontSize: 13,
              marginBottom: 12,
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || timeLeft <= 0}
            style={{ width: '100%', justifyContent: 'center', padding: 13 }}
          >
            {loading ? 'Verifying…' : 'Verify & Continue →'}
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
