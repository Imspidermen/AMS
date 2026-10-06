import { Component, lazy, Suspense, type ErrorInfo, type ReactNode } from 'react';
import { Navigate, Route, Routes, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './lib/auth';
import { Loading, Notice } from './components/ui';

const Layout = lazy(() => import('./components/Layout').then((module) => ({ default: module.Layout })));
const LoginPage = lazy(() => import('./pages/Login').then((module) => ({ default: module.LoginPage })));
const ActivationPage = lazy(() => import('./pages/Login').then((module) => ({ default: module.ActivationPage })));
const AdminDashboard = lazy(() => import('./pages/Dashboards').then((module) => ({ default: module.AdminDashboard })));
const TeacherDashboard = lazy(() => import('./pages/Dashboards').then((module) => ({ default: module.TeacherDashboard })));
const StudentDashboard = lazy(() => import('./pages/Dashboards').then((module) => ({ default: module.StudentDashboard })));
const PeoplePage = lazy(() => import('./pages/Admin').then((module) => ({ default: module.PeoplePage })));
const AcademicsPage = lazy(() => import('./pages/Admin').then((module) => ({ default: module.AcademicsPage })));
const LocationsPage = lazy(() => import('./pages/Admin').then((module) => ({ default: module.LocationsPage })));
const AdminAttendancePage = lazy(() => import('./pages/Admin').then((module) => ({ default: module.AdminAttendancePage })));
const CorrectionsPage = lazy(() => import('./pages/Admin').then((module) => ({ default: module.CorrectionsPage })));
const AuditPage = lazy(() => import('./pages/Admin').then((module) => ({ default: module.AuditPage })));
const SystemPage = lazy(() => import('./pages/Admin').then((module) => ({ default: module.SystemPage })));
const MarkAttendancePage = lazy(() => import('./pages/Student').then((module) => ({ default: module.MarkAttendancePage })));
const StudentAttendancePage = lazy(() => import('./pages/Student').then((module) => ({ default: module.StudentAttendancePage })));
const StudentProfilePage = lazy(() => import('./pages/Student').then((module) => ({ default: module.StudentProfilePage })));
const StudentCorrectionsPage = lazy(() => import('./pages/Student').then((module) => ({ default: module.StudentCorrectionsPage })));
const TeacherClassesPage = lazy(() => import('./pages/Teacher').then((module) => ({ default: module.TeacherClassesPage })));
const TeacherWatchPage = lazy(() => import('./pages/Teacher').then((module) => ({ default: module.TeacherWatchPage })));
const TeacherCorrectionsPage = lazy(() => import('./pages/Teacher').then((module) => ({ default: module.TeacherCorrectionsPage })));
const NotificationsPage = lazy(() => import('./pages/Notifications').then((module) => ({ default: module.NotificationsPage })));
const PrivacyPage = lazy(() => import('./pages/Privacy').then((module) => ({ default: module.PrivacyPage })));

const home = { admin: '/admin', teacher: '/teacher', student: '/student' } as const;

function PublicOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return user ? <Navigate to={home[user.role]} replace /> : children;
}

function RoleRoute({ role }: { role: 'admin' | 'teacher' | 'student' }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (user.role !== role) return <Navigate to={home[user.role]} replace />;
  return <Outlet />;
}

function AuthRoute() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('SSAMS view error', error.name, info.componentStack); }
  render() {
    if (this.state.failed) return <div className="error-boundary"><Notice kind="error">This page encountered an unexpected error. Reload the page or return to your dashboard.</Notice><button className="button button-secondary" onClick={() => window.location.reload()}>Reload page</button></div>;
    return this.props.children;
  }
}

export function App() {
  return <ErrorBoundary><Suspense fallback={<Loading />}><Routes>
    <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
    <Route path="/activate" element={<ActivationPage />} />
    <Route path="/privacy" element={<PrivacyPage />} />
    <Route element={<AuthRoute />}>
      <Route element={<Layout />}>
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/help" element={<HelpPage />} />
      </Route>
      <Route element={<RoleRoute role="admin" />}>
        <Route element={<Layout />}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/people" element={<PeoplePage />} />
          <Route path="/admin/academics" element={<AcademicsPage />} />
          <Route path="/admin/locations" element={<LocationsPage />} />
          <Route path="/admin/attendance" element={<AdminAttendancePage />} />
          <Route path="/admin/corrections" element={<CorrectionsPage />} />
          <Route path="/admin/audit" element={<AuditPage />} />
          <Route path="/admin/system" element={<SystemPage />} />
        </Route>
      </Route>
      <Route element={<RoleRoute role="teacher" />}>
        <Route element={<Layout />}>
          <Route path="/teacher" element={<TeacherDashboard />} />
          <Route path="/teacher/classes" element={<TeacherClassesPage />} />
          <Route path="/teacher/low-attendance" element={<TeacherWatchPage />} />
          <Route path="/teacher/corrections" element={<TeacherCorrectionsPage />} />
        </Route>
      </Route>
      <Route element={<RoleRoute role="student" />}>
        <Route element={<Layout />}>
          <Route path="/student" element={<StudentDashboard />} />
          <Route path="/student/mark" element={<MarkAttendancePage />} />
          <Route path="/student/attendance" element={<StudentAttendancePage />} />
          <Route path="/student/profile" element={<StudentProfilePage />} />
          <Route path="/student/corrections" element={<StudentCorrectionsPage />} />
        </Route>
      </Route>
      <Route path="/" element={<HomeRedirect />} />
    </Route>
    <Route path="*" element={<NotFound />} />
  </Routes></Suspense></ErrorBoundary>;
}

function HomeRedirect() {
  const { user } = useAuth();
  return <Navigate to={user ? home[user.role] : '/login'} replace />;
}

function HelpPage() {
  return <main><div className="page-header"><div><div className="eyebrow">SUPPORT</div><h1>Help & guidance</h1><p>Quick checks for account access, camera and location permissions.</p></div></div>
    <div className="grid-two">
      <section className="card"><h2>Camera and location</h2><p>Attendance uses the device camera and browser location only after you select a scheduled class and start verification. No video is stored.</p><ul className="help-list"><li>Use the application over HTTPS for camera and location access on phones.</li><li>Allow camera and location access for this site in your browser settings.</li><li>Use a well-lit area and hold still between the requested movements.</li><li>GPS accuracy varies indoors. Move near a window or ask your instructor for help.</li></ul></section>
      <section className="card"><h2>Account and attendance records</h2><p>Student IDs, account activation and password resets are managed by an administrator. Teachers see only assigned classes.</p><ul className="help-list"><li>Activation links expire after seven days; password reset links expire after 24 hours.</li><li>Use a correction request if a recorded status needs review.</li><li>For repeated verification failures, ask a teacher or administrator to review your case.</li></ul></section>
    </div>
  </main>;
}

function NotFound() {
  return <div className="not-found"><div className="not-found-code">404</div><h1>That page isn’t here</h1><p>The link may have changed, or you may not have access to this workspace.</p><a className="button button-primary" href="/">Return to SSAMS</a></div>;
}
