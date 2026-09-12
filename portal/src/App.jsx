import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';

// Auth
import LoginPage from './auth/LoginPage';
import RegisterPage from './auth/RegisterPage';
import DemoToolkit from './components/DemoToolkit';

// Layouts
import StudentLayout from './layouts/StudentLayout';
import AdminLayout from './layouts/AdminLayout';

// Student Pages
import StudentDashboard from './student/StudentDashboard';
import MyActivity from './student/MyActivity';
import MyRiskProfile from './student/MyRiskProfile';
import StudentNotifications from './student/StudentNotifications';

// Admin Pages
import CommandCenter from './admin/CommandCenter';
import PipelineMonitor from './admin/PipelineMonitor';
import IncidentManager from './admin/IncidentManager';
import UserManagement from './admin/UserManagement';
import AlertFeed from './admin/AlertFeed';
import ThreatAnalytics from './admin/ThreatAnalytics';
import PolicyControl from './admin/PolicyControl';
import ApiSandbox from './admin/ApiSandbox';

// ─── Route Guards ─────────────────────────────────────────────────────────────

/** Requires auth. If not logged in, redirect to /login. */
function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-center"><div className="loading-spinner" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

/** Requires specific role(s). Falls back to correct portal if wrong role. */
function RequireRole({ roles, children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) {
    // Redirect to correct portal
    if (user.role === 'admin' || user.role === 'manager') return <Navigate to="/admin" replace />;
    return <Navigate to="/student" replace />;
  }
  return children;
}

/** Smart root redirect based on role */
function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-center"><div className="loading-spinner" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === 'admin' || user.role === 'manager') return <Navigate to="/admin" replace />;
  return <Navigate to="/student" replace />;
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter basename="/portal">
      <AuthProvider>
        <Routes>
          {/* Root: smart redirect based on role */}
          <Route path="/" element={<RootRedirect />} />

          {/* Login / Register */}
          <Route path="/login" element={<LoginRedirect />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Student Portal */}
          <Route
            path="/student"
            element={
              <RequireAuth>
                <RequireRole roles={['student', 'admin', 'manager']}>
                  <StudentLayout />
                </RequireRole>
              </RequireAuth>
            }
          >
            <Route index element={<StudentDashboard />} />
            <Route path="activity" element={<MyActivity />} />
            <Route path="profile" element={<MyRiskProfile />} />
            <Route path="alerts" element={<StudentNotifications />} />
          </Route>

          {/* Admin Portal */}
          <Route
            path="/admin"
            element={
              <RequireAuth>
                <RequireRole roles={['admin', 'manager']}>
                  <AdminLayout />
                </RequireRole>
              </RequireAuth>
            }
          >
            <Route index element={<CommandCenter />} />
            <Route path="pipeline" element={<PipelineMonitor />} />
            <Route path="incidents" element={<IncidentManager />} />
            <Route path="users" element={<UserManagement />} />
            <Route path="alerts" element={<AlertFeed />} />
            <Route path="analytics" element={<ThreatAnalytics />} />
            <Route path="policy" element={<PolicyControl />} />
            <Route path="sandbox" element={<ApiSandbox />} />
          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <DemoToolkit />
      </AuthProvider>
    </BrowserRouter>
  );
}

/** If already logged in, skip the login page and go to correct portal */
function LoginRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-center"><div className="loading-spinner" /></div>;
  if (user) {
    if (user.role === 'admin' || user.role === 'manager') return <Navigate to="/admin" replace />;
    return <Navigate to="/student" replace />;
  }
  return <LoginPage />;
}
