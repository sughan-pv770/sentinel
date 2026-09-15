import { useState, useEffect } from 'react';
import { useAuth } from './AuthContext';
import { Shield, AlertTriangle } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

const DEMO_ACCOUNTS = [
  { id: 'u_admin', label: 'Admin — Priya Nair', role: 'admin', password: 'admin123' },
  { id: 'u_manager1', label: 'Manager — Prof. Smith', role: 'manager', password: 'manager123' },
  { id: 'u_alex', label: 'Student — Alex Rao', role: 'student', password: 'student123' },
  { id: 'u_mina', label: 'Student — Mina Okafor', role: 'student', password: 'student123' },
];

const REASON_MESSAGES = {
  session_revoked: 'Your session was terminated by the security system.',
  rate_burst_surge: 'Your session was terminated due to abnormal request activity.',
  impossible_travel: 'Your session was terminated due to suspicious geographic activity.',
  admin_forced_revocation: 'Your session was terminated by a system administrator.',
  anomaly_detected: 'Your session was terminated due to detected anomalous behavior.',
  token_used_after_revocation: 'Your session token was invalidated.',
};

export default function LoginPage() {
  const { login, forceLogoutReason, clearForceLogout } = useAuth();
  const [searchParams] = useSearchParams();
  const [identity_id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Determine if there's a security alert to show
  const urlReason = searchParams.get('reason');
  const alertReason = forceLogoutReason || urlReason;
  const alertMessage = alertReason
    ? REASON_MESSAGES[alertReason] || 'Your session was terminated for security reasons.'
    : null;

  // Clear force logout on unmount
  useEffect(() => {
    return () => clearForceLogout?.();
  }, [clearForceLogout]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(identity_id.trim(), password);
    } catch (err) {
      setError(err.data?.detail || 'Invalid credentials. Try a demo account below.');
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = (account) => {
    setId(account.id);
    setPassword(account.password);
    setError('');
  };

  return (
    <>
      {/* Ambient background */}
      <div className="ambient-bg">
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div className="orb orb-3" />
      </div>

      <div className="login-page">
        <div className="login-card animate-fade-in">
          {/* Security Alert Banner */}
          {alertMessage && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              borderRadius: '10px',
              padding: '14px 16px',
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
            }}>
              <AlertTriangle size={20} color="#ef4444" style={{ flexShrink: 0, marginTop: 2 }} />
              <div>
                <div style={{ color: '#ef4444', fontWeight: 600, fontSize: '13px', marginBottom: '4px' }}>
                  Security Alert
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '12px', lineHeight: '1.5' }}>
                  {alertMessage} Please sign in again to continue.
                </div>
              </div>
            </div>
          )}

          {/* Logo */}
          <div className="login-logo">
            <div className="login-logo-icon">
              <Shield size={28} color="white" strokeWidth={1.5} />
            </div>
            <div className="login-logo-text">
              <h1>SentinelX</h1>
              <span>Zero Trust Security Platform</span>
            </div>
          </div>

          {/* Heading */}
          <p className="login-title">Welcome back</p>
          <p className="login-sub">Sign in to access your security portal</p>

          {/* Form */}
          <form className="login-form" onSubmit={handleSubmit}>
            <div>
              <label>Identity ID</label>
              <input
                className="input"
                type="text"
                value={identity_id}
                onChange={e => setId(e.target.value)}
                placeholder="e.g. u_alex"
                autoComplete="username"
                required
              />
            </div>
            <div>
              <label>Password</label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
              />
            </div>

            {error && <div className="login-error">{error}</div>}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
            >
              {loading ? 'Authenticating…' : 'Sign In →'}
            </button>
          </form>

          {/* Demo accounts */}
          <div className="login-demo-accounts">
            <div className="demo-label">Quick Demo Access</div>
            <div className="demo-chips">
              {DEMO_ACCOUNTS.map(acct => (
                <button
                  key={acct.id}
                  className="demo-chip"
                  onClick={() => fillDemo(acct)}
                  title={`${acct.label} / ${acct.password}`}
                >
                  {acct.id}
                </button>
              ))}
            </div>
            <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '10px' }}>
              Click any account above to auto-fill credentials, then Sign In.
            </p>
            
            <div style={{ textAlign: 'center', marginTop: '24px', fontSize: '13px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Don't have an account? </span>
              <Link to="/register" style={{ color: 'var(--brand-primary)', textDecoration: 'none', fontWeight: 600 }}>
                Create one now
              </Link>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
