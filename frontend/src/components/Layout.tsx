import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  BookOpen, CalendarDays, ChartNoAxesCombined, CheckCheck, ChevronDown,
  CircleHelp, ClipboardCheck, LayoutDashboard, LogOut, MapPinned, Menu, School, Settings2,
  ShieldCheck, UserRound, Users, Bell, X,
} from 'lucide-react';
import { useAuth } from '../lib/auth';
import { api, DEFAULT_CAMPUS_TIMEZONE, setCampusTimezone } from '../lib/api';

const nav = {
  admin: [
    { label: 'Overview', to: '/admin', icon: LayoutDashboard, end: true },
    { label: 'People', to: '/admin/people', icon: Users },
    { label: 'Academic setup', to: '/admin/academics', icon: BookOpen },
    { label: 'Locations & schedules', to: '/admin/locations', icon: MapPinned },
    { label: 'Attendance & reports', to: '/admin/attendance', icon: ChartNoAxesCombined },
    { label: 'Correction review', to: '/admin/corrections', icon: CheckCheck },
    { label: 'Audit trail', to: '/admin/audit', icon: ShieldCheck },
    { label: 'Policy & health', to: '/admin/system', icon: Settings2 },
  ],
  teacher: [
    { label: 'Overview', to: '/teacher', icon: LayoutDashboard, end: true },
    { label: 'My classes', to: '/teacher/classes', icon: CalendarDays },
    { label: 'Attendance watch', to: '/teacher/low-attendance', icon: ChartNoAxesCombined },
    { label: 'Correction review', to: '/teacher/corrections', icon: CheckCheck },
    { label: 'Notifications', to: '/notifications', icon: Bell },
  ],
  student: [
    { label: 'Overview', to: '/student', icon: LayoutDashboard, end: true },
    { label: 'Mark attendance', to: '/student/mark', icon: ClipboardCheck },
    { label: 'My attendance', to: '/student/attendance', icon: ChartNoAxesCombined },
    { label: 'Correction requests', to: '/student/corrections', icon: CheckCheck },
    { label: 'My profile', to: '/student/profile', icon: UserRound },
    { label: 'Notifications', to: '/notifications', icon: Bell },
  ],
};

const home = { admin: '/admin', teacher: '/teacher', student: '/student' } as const;

export function Layout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [, setTimezoneRevision] = useState(0);
  const unread = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => api<{ unread: number }>('/notifications?limit=1'),
    refetchInterval: 60_000,
  });
  const campus = useQuery({ queryKey: ['campus-health'], queryFn: () => api<{campus_timezone:string}>('/health/live'), retry: false });
  useEffect(() => {
    if (campus.data?.campus_timezone) {
      setCampusTimezone(campus.data.campus_timezone);
      setTimezoneRevision((revision) => revision + 1);
    }
  }, [campus.data?.campus_timezone]);
  if (!user) return null;
  const roleLinks = nav[user.role];
  const title = roleLinks.find((item) => item.end ? item.to === location.pathname : location.pathname.startsWith(item.to))?.label || 'Workspace';
  const initials = user.full_name.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0]).join('').toUpperCase();

  async function handleSignOut() {
    try { await signOut(); } finally { navigate('/login', { replace: true }); }
  }

  return <div className="app-frame">
    <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
      <div className="brand-lockup">
        <Link to={home[user.role]} className="brand-mark" aria-label="SSAMS home"><School size={22} strokeWidth={2.2} /></Link>
        <div><strong>SSAMS</strong><span>Campus attendance</span></div>
        <button className="icon-button sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X size={18} /></button>
      </div>
      <div className="workspace-label">WORKSPACE</div>
      <nav className="side-nav" aria-label={`${user.role} navigation`}>
        {roleLinks.map(({ label, to, icon: Icon, end }) => <NavLink key={to} to={to} end={end}
          className={({ isActive }) => `nav-link ${isActive ? 'nav-active' : ''}`} onClick={() => setMenuOpen(false)}>
          <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
          {label === 'Notifications' && (unread.data?.unread ?? 0) > 0 && <b className="nav-count">{unread.data?.unread}</b>}
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="privacy-note"><ShieldCheck size={16} /><span>Verification is private and processed on this institution’s server.</span></div>
        <button className="sidebar-help" onClick={() => navigate('/help')}><CircleHelp size={17} /> Help & guidance</button>
        <div className="sidebar-foot">SSAMS · Locally operated<br />Times stored as UTC · displayed in {campus.data?.campus_timezone || DEFAULT_CAMPUS_TIMEZONE}</div>
      </div>
    </aside>
    {menuOpen && <button className="scrim" onClick={() => setMenuOpen(false)} aria-label="Close navigation overlay" />}
    <main className="main-area">
      <header className="topbar">
        <div className="topbar-left">
          <button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <span className="breadcrumb-root">SSAMS</span><span className="breadcrumb-sep">/</span><span className="breadcrumb-current">{title}</span>
        </div>
        <div className="topbar-right">
          <Link to="/notifications" className="icon-button notification-button" aria-label="Notifications">
            <Bell size={19} />{(unread.data?.unread ?? 0) > 0 && <i className="notification-dot" />}
          </Link>
          <div className="profile-menu-wrap">
            <button className="profile-trigger" onClick={() => setProfileOpen(!profileOpen)} aria-expanded={profileOpen}>
              <span className="avatar">{initials}</span><span className="profile-copy"><strong>{user.full_name}</strong><small>{user.role}</small></span><ChevronDown size={15} />
            </button>
            {profileOpen && <div className="profile-dropdown">
              <div className="dropdown-account"><strong>{user.full_name}</strong><span>{user.email}</span></div>
              {user.role === 'student' && <Link to="/student/profile" onClick={() => setProfileOpen(false)}><UserRound size={15} /> Profile</Link>}
              <button onClick={() => void handleSignOut()}><LogOut size={15} /> Sign out</button>
            </div>}
          </div>
        </div>
      </header>
      <div className="page-wrap"><Outlet /></div>
      <footer className="mobile-footer">SSAMS · Smart Student Attendance Management</footer>
    </main>
  </div>;
}
