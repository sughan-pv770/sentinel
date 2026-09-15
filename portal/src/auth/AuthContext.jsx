import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { auth as authApi } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [forceLogoutReason, setForceLogoutReason] = useState(null);
  const eventSourceRef = useRef(null);

  // Check for existing session on mount
  useEffect(() => {
    authApi.me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // ── SSE: Real-time session termination listener ─────────────────────────────
  useEffect(() => {
    if (!user) {
      // Close SSE when not authenticated
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return;
    }

    // Open SSE stream for session events
    const es = new EventSource('/api/events/session', { withCredentials: true });
    eventSourceRef.current = es;

    es.addEventListener('session_terminated', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.warn('[SentinelX] Session terminated by server:', data);
        setForceLogoutReason(data.reason || 'session_revoked');
        // Immediately clear user state and redirect to login
        setUser(null);
        authApi.logout().catch(() => {});
      } catch (err) {
        console.error('[SentinelX] Failed to parse SSE event:', err);
        setForceLogoutReason('session_revoked');
        setUser(null);
      }
    });

    es.addEventListener('risk_update', (event) => {
      try {
        const data = JSON.parse(event.data);
        // Optional: update live risk badge in the UI
        console.info('[SentinelX] Risk update:', data);
      } catch (err) {
        // Ignore parse errors for non-critical events
      }
    });

    es.onerror = (err) => {
      // EventSource auto-reconnects; log for observability
      console.warn('[SentinelX] SSE connection error, will auto-reconnect');
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [user]);

  const login = useCallback(async (identity_id, password) => {
    setForceLogoutReason(null);
    const data = await authApi.login(identity_id, password);
    setUser(data);
    return data;
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout().catch(() => {});
    setUser(null);
  }, []);

  const clearForceLogout = useCallback(() => {
    setForceLogoutReason(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, forceLogoutReason, clearForceLogout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
