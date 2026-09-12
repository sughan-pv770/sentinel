import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import {
  LayoutDashboard, Activity, Fingerprint, Bell, LogOut, Shield
} from 'lucide-react';

const NAV = [
  { to: '/student',          icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/student/activity', icon: Activity,         label: 'My Activity' },
  { to: '/student/profile',  icon: Fingerprint,      label: 'Risk Profile' },
  { to: '/student/alerts',   icon: Bell,             label: 'Notifications' },
];

export default function StudentLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const initials = user?.name
    ? user.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : (user?.identity_id || 'S').toUpperCase().slice(0, 2);

  return (
    <div className="portal-shell">
      {/* Ambient */}
      <div className="ambient-bg">
        <div className="orb orb-1" style={{ opacity: 0.06 }} />
        <div className="orb orb-2" style={{ opacity: 0.06 }} />
      </div>

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <Shield size={20} color="white" strokeWidth={1.5} />
          </div>
          <div className="sidebar-brand-text">
            <div className="sidebar-brand-name">SentinelX</div>
            <div className="sidebar-brand-sub">Student Portal</div>
          </div>
        </div>

        <div className="sidebar-section-label">Navigation</div>
        <nav className="sidebar-nav">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/student'}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <Icon size={18} className="nav-icon" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user" onClick={handleLogout} title="Click to log out">
            <div className="user-avatar">{initials}</div>
            <div className="user-info">
              <div className="user-name">{user?.name || user?.identity_id}</div>
              <div className="user-role">{user?.role || 'student'} — logout</div>
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
