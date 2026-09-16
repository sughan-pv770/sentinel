/**
 * AuthContext — Production session management with progressive security UX.
 *
 * Security event escalation ladder:
 *
 *  restrict (1st time) → small toast in bottom-right corner (non-blocking, auto-dismisses 7s)
 *  restrict (2nd time) → soft card modal: "We're keeping a close eye on your account"
 *  revoke             → graceful 10s countdown screen → server logout → login with reason
 *
 * The student always knows what's happening, why, and what to do next.
 * No jarring interruptions — every transition is animated and explained.
 */
import {
  createContext, useContext, useState, useEffect,
  useCallback, useRef,
} from 'react';
import { auth as authApi } from '../api/client';
import { ShieldAlert, ShieldCheck, X, LogOut, AlertTriangle } from 'lucide-react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]                           = useState(null);
  const [loading, setLoading]                     = useState(true);
  const [forceLogoutReason, setForceLogoutReason] = useState(null);
  const [pendingMfaChallenge, setPendingMfaChallenge] = useState(null);

  // Restrict warning progression: 0 = none, 1 = toast shown, 2 = modal shown
  const [warnCount, setWarnCount]     = useState(0);
  const [showToast, setShowToast]     = useState(false);
  const [toastData, setToastData]     = useState(null);
  const [showWarnModal, setShowWarnModal] = useState(false);
  const [warnModalData, setWarnModalData] = useState(null);

  // Revoke: shows countdown screen before hard logout
  const [revokeCountdown, setRevokeCountdown] = useState(null);
  // { reason, message, seconds }

  const eventSourceRef = useRef(null);
  const toastTimerRef  = useRef(null);
  const revokeTimerRef = useRef(null);

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  useEffect(() => {
    authApi.me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // ── Revoke countdown tick ──────────────────────────────────────────────────
  useEffect(() => {
    if (!revokeCountdown) return;
    if (revokeCountdown.seconds <= 0) {
      // Time's up — actually log out now
      clearInterval(revokeTimerRef.current);
      setUser(null);
      authApi.logout().catch(() => {});
      return;
    }
    const t = setTimeout(() => {
      setRevokeCountdown(prev => prev ? { ...prev, seconds: prev.seconds - 1 } : null);
    }, 1000);
    revokeTimerRef.current = t;
    return () => clearTimeout(t);
  }, [revokeCountdown]);

  // ── SSE per-identity listener ──────────────────────────────────────────────
  useEffect(() => {
    if (!user) {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      return;
    }

    const es = new EventSource('/api/events/session', { withCredentials: true });
    eventSourceRef.current = es;

    // ── REVOKE → graceful countdown, then logout ───────────────────────────
    es.addEventListener('session_terminated', (event) => {
      try {
        const data = JSON.parse(event.data);
        const reasonMap = {
          anomaly_detected:    'Suspicious activity was detected on your account.',
          frequency_spike:     'An unusually high number of requests were made in a short time.',
          impossible_travel:   'A login was detected from an unexpected location.',
          privilege_escalation:'An attempt to access restricted resources was flagged.',
          session_revoked:     'Your session was terminated by a security policy.',
        };
        const msg = reasonMap[data.reason] || 'Our security system flagged unusual activity.';

        // Clear any existing warnings
        setShowToast(false);
        setShowWarnModal(false);
        clearTimeout(toastTimerRef.current);

        // Start graceful 10-second countdown
        setRevokeCountdown({
          reason:  data.reason || 'session_revoked',
          message: msg,
          seconds: 10,
          risk_score: data.risk_score,
        });
        setForceLogoutReason(data.reason || 'session_revoked');
      } catch {
        setRevokeCountdown({ reason: 'session_revoked', message: 'Your session was terminated.', seconds: 10 });
        setForceLogoutReason('session_revoked');
      }
    });

    // ── RESTRICT → progressive warning (toast → modal) ─────────────────────
    es.addEventListener('session_restricted', (event) => {
      try {
        const data = JSON.parse(event.data);
        setWarnCount(prev => {
          const next = prev + 1;
          if (next === 1) {
            // First warning: subtle toast in corner
            setToastData({
              message: data.message || 'Unusual activity detected on your account.',
              risk_score: data.risk_score,
            });
            setShowToast(true);
            clearTimeout(toastTimerRef.current);
            toastTimerRef.current = setTimeout(() => setShowToast(false), 7000);
          } else {
            // Second+ warning: soft modal
            setShowToast(false);
            clearTimeout(toastTimerRef.current);
            setWarnModalData({
              count: next,
              message: data.message || 'We\'ve noticed continued unusual activity on your account.',
              risk_score: data.risk_score,
            });
            setShowWarnModal(true);
          }
          return next;
        });
      } catch { /* ignore */ }
    });

    // ── STEP_UP → show MFA modal immediately ──────────────────────────────
    es.addEventListener('mfa_challenge', (event) => {
      try {
        const data = JSON.parse(event.data);
        setPendingMfaChallenge(data.challenge || { method: 'totp', ttl_seconds: 300 });
      } catch {
        setPendingMfaChallenge({ method: 'totp', ttl_seconds: 300 });
      }
    });

    es.addEventListener('risk_update', () => {});
    es.onerror = () => {};

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [user]);

  const login = useCallback(async (identity_id, password) => {
    setForceLogoutReason(null);
    setPendingMfaChallenge(null);
    setWarnCount(0);
    setShowToast(false);
    setShowWarnModal(false);
    setRevokeCountdown(null);
    const data = await authApi.login(identity_id, password);
    setUser(data);
    return data;
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout().catch(() => {});
    setUser(null);
    setPendingMfaChallenge(null);
    setRevokeCountdown(null);
  }, []);

  const clearForceLogout  = useCallback(() => setForceLogoutReason(null), []);
  const clearMfaChallenge = useCallback(() => setPendingMfaChallenge(null), []);
  const dismissToast      = useCallback(() => { setShowToast(false); clearTimeout(toastTimerRef.current); }, []);
  const dismissWarnModal  = useCallback(() => setShowWarnModal(false), []);

  return (
    <AuthContext.Provider value={{
      user, loading, login, logout,
      forceLogoutReason, clearForceLogout,
      pendingMfaChallenge, clearMfaChallenge,
    }}>
      {children}

      {/* ── Warning Toast (1st restrict) ───────────────────────────────────── */}
      <WarningToast show={showToast} data={toastData} onDismiss={dismissToast} />

      {/* ── Warning Modal (2nd+ restrict) ─────────────────────────────────── */}
      {showWarnModal && (
        <WarningModal data={warnModalData} onDismiss={dismissWarnModal} />
      )}

      {/* ── Revoke Countdown Screen ────────────────────────────────────────── */}
      {revokeCountdown && (
        <RevokeCountdown data={revokeCountdown} />
      )}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}


// ── Warning Toast — non-blocking, slides in from bottom-right ─────────────────

function WarningToast({ show, data, onDismiss }) {
  return (
    <>
      <style>{`
        @keyframes toast-in  { from { opacity:0; transform:translateX(120%); } to { opacity:1; transform:translateX(0); } }
        @keyframes toast-out { from { opacity:1; transform:translateX(0); } to { opacity:0; transform:translateX(120%); } }
        .sentinelx-toast { animation: toast-in 0.4s cubic-bezier(0.16,1,0.3,1) forwards; }
        .sentinelx-toast.hide { animation: toast-out 0.35s ease forwards; }
      `}</style>
      {show && data && (
        <div
          className={`sentinelx-toast${show ? '' : ' hide'}`}
          style={{
            position: 'fixed', bottom: 24, right: 24,
            zIndex: 9990,
            background: 'var(--surface, #1e1e2e)',
            border: '1px solid rgba(245,158,11,0.3)',
            borderLeft: '3px solid #f59e0b',
            borderRadius: 12,
            padding: '14px 16px',
            maxWidth: 320, width: '100%',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            display: 'flex', gap: 12, alignItems: 'flex-start',
          }}
        >
          <div style={{
            width: 32, height: 32, borderRadius: 8, flexShrink: 0,
            background: 'rgba(245,158,11,0.12)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <AlertTriangle size={16} color="#f59e0b" />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary,#fff)', marginBottom: 3 }}>
              Security Notice
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary,#94a3b8)', lineHeight: 1.5 }}>
              {data.message}
            </div>
          </div>
          <button onClick={onDismiss} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted,#64748b)', padding: 2, flexShrink: 0,
          }}>
            <X size={14} />
          </button>
        </div>
      )}
    </>
  );
}


// ── Warning Modal — soft 2nd warning, not full-screen ────────────────────────

function WarningModal({ data, onDismiss }) {
  const isFinal = data?.count >= 2;
  return (
    <>
      <style>{`
        @keyframes warn-modal-in {
          from { opacity:0; transform:translateY(-12px) scale(0.97); }
          to   { opacity:1; transform:translateY(0) scale(1); }
        }
        .warn-modal-card { animation: warn-modal-in 0.3s cubic-bezier(0.16,1,0.3,1) forwards; }
      `}</style>
      <div style={{
        position: 'fixed', inset: 0, zIndex: 9995,
        background: 'rgba(0,0,0,0.55)',
        backdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16,
      }}>
        <div className="warn-modal-card" style={{
          background: 'var(--surface,#1e1e2e)',
          border: `1px solid ${isFinal ? 'rgba(239,68,68,0.25)' : 'rgba(245,158,11,0.25)'}`,
          borderRadius: 18, padding: '28px 28px 24px',
          maxWidth: 420, width: '100%',
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
          position: 'relative',
        }}>
          {/* Top accent bar */}
          <div style={{
            position: 'absolute', top: 0, left: 0, right: 0, height: 3,
            borderRadius: '18px 18px 0 0',
            background: isFinal
              ? 'linear-gradient(90deg,#ef4444,#dc2626)'
              : 'linear-gradient(90deg,#f59e0b,#d97706)',
          }} />

          <div style={{ display: 'flex', gap: 14, marginBottom: 16, marginTop: 4 }}>
            <div style={{
              width: 44, height: 44, borderRadius: 12, flexShrink: 0,
              background: isFinal ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: `1px solid ${isFinal ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}`,
            }}>
              <ShieldAlert size={20} color={isFinal ? '#ef4444' : '#f59e0b'} />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary,#fff)', marginBottom: 4 }}>
                {isFinal ? 'Final Warning' : 'Security Alert'}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted,#64748b)' }}>
                {isFinal
                  ? 'Continued violations may result in your session being terminated.'
                  : 'We\'re monitoring your session for your security.'}
              </div>
            </div>
          </div>

          <p style={{ fontSize: 13, color: 'var(--text-secondary,#94a3b8)', lineHeight: 1.6, marginBottom: 20 }}>
            {data?.message}
            {isFinal && (
              <><br /><br />
                <strong style={{ color: isFinal ? '#f87171' : '#fbbf24' }}>
                  Please slow down or contact your administrator if you need assistance.
                </strong>
              </>
            )}
          </p>

          {data?.risk_score && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              marginBottom: 18, padding: '8px 12px',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 8,
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted,#64748b)', marginBottom: 4 }}>
                  Current risk level
                </div>
                <div style={{
                  height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%', borderRadius: 4,
                    width: `${Math.min(data.risk_score, 100)}%`,
                    background: isFinal
                      ? 'linear-gradient(90deg,#ef4444,#dc2626)'
                      : 'linear-gradient(90deg,#f59e0b,#ef4444)',
                    transition: 'width 0.5s ease',
                  }} />
                </div>
              </div>
              <span style={{
                fontSize: 13, fontWeight: 700,
                color: isFinal ? '#f87171' : '#fbbf24',
                minWidth: 36, textAlign: 'right',
              }}>
                {Math.round(data.risk_score)}%
              </span>
            </div>
          )}

          <button
            onClick={onDismiss}
            style={{
              width: '100%', padding: '12px',
              background: isFinal
                ? 'rgba(239,68,68,0.1)'
                : 'rgba(245,158,11,0.1)',
              border: `1px solid ${isFinal ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}`,
              borderRadius: 10,
              color: isFinal ? '#f87171' : '#fbbf24',
              fontSize: 13, fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            I understand — dismiss
          </button>
        </div>
      </div>
    </>
  );
}


// ── Revoke Countdown Screen — graceful, informative, 10-second exit ───────────

function RevokeCountdown({ data }) {
  const pct = Math.max(0, (data.seconds / 10) * 100);
  const circumference = 2 * Math.PI * 36; // r=36

  return (
    <>
      <style>{`
        @keyframes revoke-in {
          from { opacity:0; }
          to   { opacity:1; }
        }
        @keyframes revoke-card-in {
          from { opacity:0; transform:scale(0.94) translateY(20px); }
          to   { opacity:1; transform:scale(1) translateY(0); }
        }
      `}</style>
      <div style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        background: 'rgba(0,0,0,0.85)',
        backdropFilter: 'blur(20px)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: 24,
        animation: 'revoke-in 0.5s ease',
      }}>
        <div style={{
          maxWidth: 440, width: '100%',
          animation: 'revoke-card-in 0.5s cubic-bezier(0.16,1,0.3,1) 0.1s both',
        }}>
          {/* Circular countdown */}
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <svg width="96" height="96" viewBox="0 0 96 96" style={{ transform: 'rotate(-90deg)' }}>
              <circle cx="48" cy="48" r="36" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
              <circle
                cx="48" cy="48" r="36" fill="none"
                stroke="#ef4444" strokeWidth="5"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={circumference * (1 - pct / 100)}
                style={{ transition: 'stroke-dashoffset 0.9s linear' }}
              />
            </svg>
            <div style={{
              position: 'relative', marginTop: -70, marginBottom: 20,
              fontSize: 28, fontWeight: 700, color: '#f87171',
              fontFamily: 'monospace',
            }}>
              {data.seconds}
            </div>
          </div>

          {/* Lock icon */}
          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            <div style={{
              width: 56, height: 56, borderRadius: 16,
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.2)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 16,
            }}>
              <LogOut size={24} color="#ef4444" />
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#fff', marginBottom: 8 }}>
              Session Ending
            </div>
            <div style={{ fontSize: 14, color: 'rgba(255,255,255,0.5)', lineHeight: 1.6 }}>
              {data.message}
            </div>
          </div>

          {/* Risk bar */}
          {data.risk_score != null && (
            <div style={{
              margin: '20px 0',
              padding: '12px 16px',
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 12,
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <ShieldAlert size={16} color="#ef4444" />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 6 }}>
                  Risk score at session termination
                </div>
                <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 4 }}>
                  <div style={{
                    height: '100%', width: `${data.risk_score}%`,
                    background: 'linear-gradient(90deg,#f59e0b,#ef4444)',
                    borderRadius: 4,
                  }} />
                </div>
              </div>
              <span style={{ fontSize: 15, fontWeight: 700, color: '#f87171' }}>
                {Math.round(data.risk_score)}/100
              </span>
            </div>
          )}

          <div style={{
            textAlign: 'center', fontSize: 12,
            color: 'rgba(255,255,255,0.3)', marginTop: 20,
          }}>
            Signing you out in <strong style={{ color: 'rgba(255,255,255,0.5)' }}>{data.seconds}s</strong>
            {' '}— if you believe this is an error, contact your administrator.
          </div>
        </div>
      </div>
    </>
  );
}
