import { useState } from 'react';
import { useAuth } from './AuthContext';
import { Shield } from 'lucide-react';
import { Link } from 'react-router-dom';

const DEMO_ACCOUNTS = [
  { id: 'u_admin', label: 'Admin — Priya Nair', role: 'admin', password: 'admin123' },
  { id: 'u_manager1', label: 'Manager — Prof. Smith', role: 'manager', password: 'manager123' },
  { id: 'u_alex', label: 'Student — Alex Rao', role: 'student', password: 'student123' },
  { id: 'u_mina', label: 'Student — Mina Okafor', role: 'student', password: 'student123' },
];

export default function LoginPage() {
  const { login } = useAuth();
  const [identity_id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

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
