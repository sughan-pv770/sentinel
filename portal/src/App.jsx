import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';

// Auth
import LoginPage from './auth/LoginPage';
import RegisterPage from './auth/RegisterPage';
import MFAEnrollPage from './auth/MFAEnrollPage';
import DemoToolkit from './components/DemoToolkit';
import { MFAGateProvider } from './auth/MFAGate';

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

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-center"><div className="loading-spinner" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function RequireRole({ roles, children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) {
    if (user.role === 'admin' || user.role === 'manager') return <Navigate to="/admin" replace />;
    return <Navigate to="/student" replace />;
  }
  return children;
}

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
        <MFAGateProvider>
        <Routes>
          <Route path="/" element={<RootRedirect />} />

          {/* Login / Register / MFA */}
          <Route path="/login" element={<LoginRedirect />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/mfa/enroll" element={
            <RequireAuth><MFAEnrollPage /></RequireAuth>
          } />

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

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <DemoToolkit />
        </MFAGateProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

function LoginRedirect() {
  const { user, loading, forceLogoutReason } = useAuth();
  if (loading) return <div className="loading-center"><div className="loading-spinner" /></div>;
  if (user && !forceLogoutReason) {
    if (user.role === 'admin' || user.role === 'manager') return <Navigate to="/admin" replace />;
    return <Navigate to="/student" replace />;
  }
  return <LoginPage />;
}
