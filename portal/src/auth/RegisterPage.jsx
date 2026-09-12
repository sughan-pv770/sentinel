import { useState } from 'react';
import { useAuth } from './AuthContext';
import { Shield } from 'lucide-react';
import { useNavigate, Link } from 'react-router-dom';

export default function RegisterPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [identity_id, setId] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState('student');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // 1. Register the user
      const res = await fetch('/sentinelx/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identity_id: identity_id.trim(),
          name: name.trim(),
          role: role
        })
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to register');
      }

      // 2. Automatically log them in (default password is role + '123')
      await login(identity_id.trim(), `${role}123`);

    } catch (err) {
      setError(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
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
          <p className="login-title">Create an Account</p>
          <p className="login-sub">Register a new identity to access the portal</p>

          {/* Form */}
          <form className="login-form" onSubmit={handleSubmit}>
            <div>
              <label>Identity ID</label>
              <input
                className="input"
                type="text"
                value={identity_id}
                onChange={e => setId(e.target.value.toLowerCase().replace(/\s/g, '_'))}
                placeholder="e.g. u_newuser"
                required
              />
            </div>
            <div>
              <label>Full Name</label>
              <input
                className="input"
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. John Doe"
                required
              />
            </div>
            <div>
              <label>Role</label>
              <select 
                className="input" 
                value={role} 
                onChange={e => setRole(e.target.value)}
                style={{ appearance: 'none', backgroundColor: 'var(--bg-elevated)' }}
              >
                <option value="student">Student</option>
                <option value="manager">Manager</option>
                <option value="admin">Administrator</option>
              </select>
            </div>

            {error && <div className="login-error">{error}</div>}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              style={{ width: '100%', justifyContent: 'center', padding: '12px', marginTop: '10px' }}
            >
              {loading ? 'Registering…' : 'Create Account →'}
            </button>
            
            <div style={{ textAlign: 'center', marginTop: '20px', fontSize: '13px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Already have an account? </span>
              <Link to="/login" style={{ color: 'var(--brand-primary)', textDecoration: 'none', fontWeight: 600 }}>
                Sign In
              </Link>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
