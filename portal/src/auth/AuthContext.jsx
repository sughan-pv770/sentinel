import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { auth as authApi } from '../api/client';
import { ShieldAlert, X } from 'lucide-react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]                           = useState(null);
  const [loading, setLoading]                     = useState(true);
  const [forceLogoutReason, setForceLogoutReason] = useState(null);
  const [restrictAlert, setRestrictAlert]         = useState(null);
  // pendingMfaChallenge is read by MFAGate to show the TOTP modal immediately
  const [pendingMfaChallenge, setPendingMfaChallenge] = useState(null);
  const eventSourceRef = useRef(null);

  // ── Bootstrap: restore session on page load ────────────────────────────────
  useEffect(() => {
    authApi.me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // ── SSE: per-identity real-time session event listener ────────────────────
  // The SSE endpoint at /api/events/session authenticates via the httpOnly
  // cookie, so each client's stream is scoped ONLY to their identity_id.
  // Events from another student NEVER reach this connection.
  useEffect(() => {
    if (!user) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return;
    }

    const es = new EventSource('/api/events/session', { withCredentials: true });
    eventSourceRef.current = es;

    // ── REVOKE → hard logout (only this identity) ─────────────────────────
    es.addEventListener('session_terminated', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.warn('[SentinelX] session_terminated', data);
        setForceLogoutReason(data.reason || 'session_revoked');
        setUser(null);
        setRestrictAlert(null);
        setPendingMfaChallenge(null);
        authApi.logout().catch(() => {});
      } catch {
        setForceLogoutReason('session_revoked');
        setUser(null);
      }
    });

    // ── RESTRICT → amber warning overlay (student stays logged in) ─────────
    es.addEventListener('session_restricted', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.warn('[SentinelX] session_restricted', data);
        setRestrictAlert({
          reason:     data.reason     || 'high_risk_activity',
          message:    data.message    || 'Unusual activity detected. Your access has been temporarily restricted.',
          risk_score: data.risk_score,
        });
      } catch {
        setRestrictAlert({ reason: 'high_risk_activity', message: 'Access temporarily restricted.' });
      }
    });

    // ── STEP_UP → show TOTP/OTP modal immediately (MFAGate reads this) ────
    es.addEventListener('mfa_challenge', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.warn('[SentinelX] mfa_challenge received', data);
        setPendingMfaChallenge(data.challenge || { method: 'totp', ttl_seconds: 300 });
      } catch {
        setPendingMfaChallenge({ method: 'totp', ttl_seconds: 300 });
      }
    });

    es.addEventListener('risk_update', () => { /* could drive a live risk badge */ });

    es.onerror = () => console.warn('[SentinelX] SSE reconnecting…');

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [user]);

  const login = useCallback(async (identity_id, password) => {
    setForceLogoutReason(null);
    setRestrictAlert(null);
    setPendingMfaChallenge(null);
    const data = await authApi.login(identity_id, password);
    setUser(data);
    return data;
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout().catch(() => {});
    setUser(null);
    setRestrictAlert(null);
    setPendingMfaChallenge(null);
  }, []);

  const clearForceLogout  = useCallback(() => setForceLogoutReason(null), []);
  const dismissRestrict   = useCallback(() => setRestrictAlert(null), []);
  const clearMfaChallenge = useCallback(() => setPendingMfaChallenge(null), []);

  return (
    <AuthContext.Provider value={{
      user, loading,
      login, logout,
      forceLogoutReason, clearForceLogout,
      restrictAlert,    dismissRestrict,
      pendingMfaChallenge, clearMfaChallenge,
    }}>
      {children}

      {/* ── Restrict Warning Overlay (student stays logged in) ── */}
      {restrictAlert && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 9998,
          background: 'rgba(0,0,0,0.72)',
          backdropFilter: 'blur(10px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: 16,
        }}>
          <div style={{
            background: 'var(--surface)',
            border: '1px solid rgba(245,158,11,0.4)',
            borderRadius: 16, padding: 32,
            maxWidth: 440, width: '100%',
            boxShadow: '0 25px 60px rgba(0,0,0,0.5)',
            position: 'relative',
          }}>
            <button onClick={dismissRestrict} style={{
              position: 'absolute', top: 16, right: 16,
              background: 'transparent', border: 'none',
              color: 'var(--text-muted)', cursor: 'pointer', padding: 4,
            }}>
              <X size={18} />
            </button>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div style={{
                width: 48, height: 48, borderRadius: 12,
                background: 'rgba(245,158,11,0.15)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: '1px solid rgba(245,158,11,0.3)',
              }}>
                <ShieldAlert size={24} color="#f59e0b" />
              </div>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#f59e0b' }}>
                  Access Restricted
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  Security system has flagged your session
                </div>
              </div>
            </div>

            <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 8 }}>
              {restrictAlert.message}
            </p>

            {restrictAlert.risk_score && (
              <div style={{
                fontSize: 12, color: 'var(--text-muted)',
                background: 'rgba(255,255,255,0.04)',
                borderRadius: 8, padding: '8px 12px', marginBottom: 16,
              }}>
                Risk score:{' '}
                <strong style={{ color: '#f59e0b' }}>
                  {Math.round(restrictAlert.risk_score)}/100
                </strong>
                {' — '}your session remains active but some actions may be limited.
              </div>
            )}

            <button
              className="btn btn-primary"
              onClick={dismissRestrict}
              style={{ width: '100%', justifyContent: 'center', padding: 12 }}
            >
              I Understand — Continue
            </button>
          </div>
        </div>
      )}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
