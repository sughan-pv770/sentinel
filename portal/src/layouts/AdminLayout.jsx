import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import {
  LayoutDashboard, Cpu, AlertTriangle, Users, Bell, BarChart2,
  Settings, Terminal, LogOut, Shield
} from 'lucide-react';

const NAV = [
  { to: '/admin',             icon: LayoutDashboard, label: 'Command Center' },
  { to: '/admin/pipeline',    icon: Cpu,             label: 'ML Pipeline' },
  { to: '/admin/incidents',   icon: AlertTriangle,   label: 'Incidents',   badge: true },
  { to: '/admin/users',       icon: Users,           label: 'Users' },
  { to: '/admin/alerts',      icon: Bell,            label: 'Alert Feed' },
  { to: '/admin/analytics',   icon: BarChart2,       label: 'Analytics' },
  { to: '/admin/policy',      icon: Settings,        label: 'Policy Control' },
  { to: '/admin/sandbox',     icon: Terminal,        label: 'API Sandbox' },
];

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const initials = user?.name
    ? user.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : 'AD';

  return (
    <div className="portal-shell">
      {/* Ambient background — slightly more red for SOC feel */}
      <div className="ambient-bg">
        <div className="orb orb-1" style={{ opacity: 0.08, background: '#6366f1' }} />
        <div className="orb orb-2" style={{ opacity: 0.06, background: '#ef4444' }} />
      </div>

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <Shield size={20} color="white" strokeWidth={1.5} />
          </div>
          <div className="sidebar-brand-text">
            <div className="sidebar-brand-name">SentinelX</div>
            <div className="sidebar-brand-sub">Admin Portal</div>
          </div>
        </div>

        <div className="sidebar-section-label">Security Operations</div>
        <nav className="sidebar-nav">
          {NAV.map(({ to, icon: Icon, label, badge }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/admin'}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <Icon size={18} className="nav-icon" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div
            style={{
              padding: '8px 12px',
              marginBottom: '8px',
              borderRadius: 'var(--radius-md)',
              background: 'rgba(16,185,129,0.08)',
              border: '1px solid rgba(16,185,129,0.15)',
              display: 'flex', alignItems: 'center', gap: '8px',
            }}
          >
            <div className="status-dot online" />
            <span style={{ fontSize: '11px', color: 'var(--risk-safe)', fontWeight: 600 }}>
              Gateway Online
            </span>
          </div>

          <div className="sidebar-user" onClick={handleLogout} title="Click to log out">
            <div className="user-avatar" style={{ background: 'linear-gradient(135deg, #ef4444, #f97316)' }}>
              {initials}
            </div>
            <div className="user-info">
              <div className="user-name">{user?.name || user?.identity_id}</div>
              <div className="user-role">{user?.role || 'admin'} — logout</div>
            </div>
            <LogOut size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          </div>
        </div>
      </aside>

      {/* Content area */}
      <div className="portal-main">
        <Outlet />
      </div>
    </div>
  );
}
