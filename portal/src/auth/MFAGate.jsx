/**
 * MFAGate — Production-grade adaptive MFA interceptor.
 *
 * UX design:
 *  - Looks and feels like Duo / Okta / Google's 2-step verification
 *  - 6 separate digit boxes with auto-advance and auto-submit
 *  - Soft backdrop blur — the dashboard behind is still visible
 *  - Triggered by: secureCall(fn) API intercept OR mfa_challenge SSE event
 */
import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { mfa as mfaApi, retryPendingRequest } from '../api/client';
import { useAuth } from './AuthContext';
import { ShieldCheck, KeyRound, Clock, ArrowRight, RotateCcw } from 'lucide-react';

const MFAGateContext = createContext(null);

export function MFAGateProvider({ children }) {
  const { logout, pendingMfaChallenge, clearMfaChallenge } = useAuth();
  const [mfaState, setMfaState] = useState(null);
  const resolveRef = useRef(null);
  const rejectRef  = useRef(null);

  // Watch for SSE-pushed mfa_challenge (simulator step_up)
  useEffect(() => {
    if (pendingMfaChallenge && !mfaState) {
      setMfaState({ challenge: pendingMfaChallenge, pendingError: null });
    }
  }, [pendingMfaChallenge]); // eslint-disable-line

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
      try { resolveRef.current?.(await retryPendingRequest(pendingError)); }
      catch (err) { rejectRef.current?.(err); }
    } else {
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

// ── Production MFA Modal ───────────────────────────────────────────────────────

function MFAModal({ challenge, pendingError, onVerified, onCancel }) {
  const NUM_DIGITS = 6;
  const [digits, setDigits]   = useState(Array(NUM_DIGITS).fill(''));
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');
  const [shake, setShake]     = useState(false);
  const [success, setSuccess] = useState(false);
  const ttl = challenge?.ttl_seconds || 300;
  const [timeLeft, setTimeLeft] = useState(ttl);
  const inputRefs = useRef([]);

  const method    = challenge?.method || 'totp';
  const sessionId = challenge?.session_id || pendingError?.data?.challenge?.session_id || '';
  const devOtp    = challenge?._dev_otp || null;

  useEffect(() => {
    if (timeLeft <= 0) return;
    const t = setInterval(() => setTimeLeft(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  // Focus first box on mount
  useEffect(() => { inputRefs.current[0]?.focus(); }, []);

  const fmt = s => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const handleDigitChange = (idx, val) => {
    const clean = val.replace(/\D/g, '').slice(-1);
    const next = [...digits];
    next[idx] = clean;
    setDigits(next);
    setError('');
    if (clean && idx < NUM_DIGITS - 1) {
      inputRefs.current[idx + 1]?.focus();
    }
    // Auto-submit when all filled
    if (clean && next.every(d => d !== '')) {
      submitCode(next.join(''));
    }
  };

  const handleKeyDown = (idx, e) => {
    if (e.key === 'Backspace' && !digits[idx] && idx > 0) {
      inputRefs.current[idx - 1]?.focus();
    }
    if (e.key === 'ArrowLeft' && idx > 0) inputRefs.current[idx - 1]?.focus();
    if (e.key === 'ArrowRight' && idx < NUM_DIGITS - 1) inputRefs.current[idx + 1]?.focus();
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, NUM_DIGITS);
    if (!pasted) return;
    const next = Array(NUM_DIGITS).fill('');
    pasted.split('').forEach((ch, i) => { next[i] = ch; });
    setDigits(next);
    inputRefs.current[Math.min(pasted.length, NUM_DIGITS - 1)]?.focus();
    if (pasted.length === NUM_DIGITS) submitCode(pasted);
  };

  const submitCode = async (code) => {
    if (loading || timeLeft <= 0) return;
    setError('');
    setLoading(true);
    try {
      if (method === 'totp') {
        await mfaApi.verifyTotp(code, sessionId, false);
      } else {
        await mfaApi.verifyOtp(code, sessionId);
      }
      setSuccess(true);
      setTimeout(() => onVerified(pendingError), 800);
    } catch (err) {
      setError(err?.data?.detail || 'Incorrect code. Please try again.');
      setShake(true);
      setTimeout(() => setShake(false), 600);
      setDigits(Array(NUM_DIGITS).fill(''));
      setTimeout(() => inputRefs.current[0]?.focus(), 50);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const code = digits.join('');
    if (code.length < NUM_DIGITS) { setError('Please enter all 6 digits'); return; }
    submitCode(code);
  };

  return (
    <>
      <style>{`
        @keyframes mfa-slide-up {
          from { opacity: 0; transform: translateY(32px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)    scale(1);    }
        }
        @keyframes mfa-backdrop-in {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes mfa-shake {
          0%,100% { transform: translateX(0); }
          20%     { transform: translateX(-8px); }
          40%     { transform: translateX(8px); }
          60%     { transform: translateX(-5px); }
          80%     { transform: translateX(5px); }
        }
        @keyframes mfa-success-pulse {
          0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.4); }
          70%  { box-shadow: 0 0 0 12px rgba(34,197,94,0); }
          100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
        }
        .mfa-digit {
          width: 48px; height: 58px;
          background: var(--surface-elevated, rgba(255,255,255,0.06));
          border: 1.5px solid var(--border, rgba(255,255,255,0.1));
          border-radius: 12px;
          font-size: 24px; font-weight: 700; font-family: monospace;
          color: var(--text-primary, #fff);
          text-align: center;
          outline: none; transition: border-color 0.15s, box-shadow 0.15s;
          caret-color: transparent;
        }
        .mfa-digit:focus {
          border-color: #6366f1;
          box-shadow: 0 0 0 3px rgba(99,102,241,0.2);
        }
        .mfa-digit.filled { border-color: rgba(99,102,241,0.6); }
        .mfa-digit.success-state { border-color: #22c55e !important; box-shadow: 0 0 0 3px rgba(34,197,94,0.2) !important; }
        .mfa-card { animation: mfa-slide-up 0.3s cubic-bezier(0.16,1,0.3,1) forwards; }
        .mfa-shake { animation: mfa-shake 0.5s ease; }
      `}</style>

      {/* Backdrop */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(16px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
        animation: 'mfa-backdrop-in 0.25s ease',
      }}>
        {/* Card */}
        <div className="mfa-card" style={{
          background: 'var(--surface, #1e1e2e)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 20, padding: '36px 32px',
          width: '100%', maxWidth: 400,
          boxShadow: '0 32px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)',
        }}>
          {/* Icon */}
          <div style={{ textAlign: 'center', marginBottom: 20 }}>
            <div style={{
              width: 64, height: 64, borderRadius: 18,
              background: success
                ? 'linear-gradient(135deg,#22c55e,#16a34a)'
                : 'linear-gradient(135deg,#6366f1,#4f46e5)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: success
                ? '0 8px 24px rgba(34,197,94,0.3)'
                : '0 8px 24px rgba(99,102,241,0.3)',
              transition: 'all 0.4s ease',
              animation: success ? 'mfa-success-pulse 0.8s ease' : 'none',
            }}>
              {success
                ? <ShieldCheck size={28} color="white" strokeWidth={1.5} />
                : <KeyRound size={28} color="white" strokeWidth={1.5} />
              }
            </div>
          </div>

          {/* Title */}
          <div style={{ textAlign: 'center', marginBottom: 6 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary,#fff)' }}>
              {success ? 'Verified!' : 'Quick Security Check'}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary,#94a3b8)', marginTop: 6, lineHeight: 1.5 }}>
              {success
                ? 'You\'re all set. Resuming your session…'
                : method === 'totp'
                  ? 'Open your authenticator app and enter the code shown'
                  : 'We sent a verification code to your registered email'}
            </div>
          </div>

          {!success && (
            <>
              {/* Dev OTP box — subtle, only in dev */}
              {devOtp && (
                <div style={{
                  margin: '16px 0',
                  padding: '10px 14px',
                  background: 'rgba(234,179,8,0.08)',
                  border: '1px dashed rgba(234,179,8,0.3)',
                  borderRadius: 10, textAlign: 'center',
                }}>
                  <span style={{ fontSize: 11, color: '#92400e', fontWeight: 500 }}>
                    Dev code:&nbsp;
                  </span>
                  <span style={{ fontFamily: 'monospace', fontSize: 18, fontWeight: 700, letterSpacing: '0.2em', color: '#fbbf24' }}>
                    {devOtp}
                  </span>
                </div>
              )}

              {/* 6-digit input boxes */}
              <form onSubmit={handleSubmit}>
                <div
                  className={shake ? 'mfa-shake' : ''}
                  style={{ display: 'flex', gap: 8, justifyContent: 'center', margin: '20px 0' }}
                >
                  {digits.map((d, i) => (
                    <input
                      key={i}
                      ref={el => inputRefs.current[i] = el}
                      className={`mfa-digit ${d ? 'filled' : ''}`}
                      type="text"
                      inputMode="numeric"
                      maxLength={1}
                      value={d}
                      onChange={e => handleDigitChange(i, e.target.value)}
                      onKeyDown={e => handleKeyDown(i, e)}
                      onPaste={i === 0 ? handlePaste : undefined}
                      disabled={loading || timeLeft <= 0}
                      autoComplete="one-time-code"
                    />
                  ))}
                </div>

                {/* Error */}
                {error && (
                  <div style={{
                    fontSize: 13, color: '#f87171', textAlign: 'center',
                    marginBottom: 12, padding: '8px 12px',
                    background: 'rgba(239,68,68,0.08)',
                    borderRadius: 8,
                  }}>
                    {error}
                  </div>
                )}

                {/* Timer row */}
                <div style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  marginBottom: 16, fontSize: 12,
                  color: timeLeft <= 30 ? '#f87171' : 'var(--text-muted,#64748b)',
                }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Clock size={12} />
                    {timeLeft > 0 ? `Expires in ${fmt(timeLeft)}` : 'Code expired'}
                  </span>
                  {method === 'email_otp' && (
                    <button type="button" onClick={onCancel} style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: '#6366f1', fontSize: 12, padding: 0,
                      display: 'flex', alignItems: 'center', gap: 4,
                    }}>
                      <RotateCcw size={11} /> Resend
                    </button>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={loading || digits.join('').length < NUM_DIGITS || timeLeft <= 0}
                  style={{
                    width: '100%', padding: '13px',
                    background: 'linear-gradient(135deg,#6366f1,#4f46e5)',
                    border: 'none', borderRadius: 12,
                    color: '#fff', fontSize: 14, fontWeight: 600,
                    cursor: loading ? 'wait' : 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    opacity: digits.join('').length < NUM_DIGITS ? 0.5 : 1,
                    transition: 'opacity 0.2s',
                    boxShadow: '0 4px 15px rgba(99,102,241,0.3)',
                  }}
                >
                  {loading ? (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{
                        width: 16, height: 16, border: '2px solid rgba(255,255,255,0.3)',
                        borderTopColor: '#fff', borderRadius: '50%',
                        animation: 'spin 0.8s linear infinite', display: 'inline-block',
                      }} />
                      Verifying…
                    </span>
                  ) : (
                    <><span>Verify</span><ArrowRight size={16} /></>
                  )}
                </button>

                <button
                  type="button"
                  onClick={onCancel}
                  style={{
                    width: '100%', marginTop: 10, padding: '11px',
                    background: 'transparent',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 12, color: 'var(--text-muted,#64748b)',
                    fontSize: 13, cursor: 'pointer',
                  }}
                >
                  Sign out instead
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </>
  );
}
