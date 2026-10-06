import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Activity, AlertTriangle, ArrowRight, BookOpen, CalendarClock, ClipboardCheck, Clock3,
  GraduationCap, MapPin, Sparkles, Users,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, formatDate, formatMonthDay, formatPercent } from '../lib/api';
import { Card, EmptyState, Loading, Notice, PageHeader, StatCard, Badge } from '../components/ui';

interface CourseSummary {
  course_id: string; course_code: string; course_name: string; threshold: number;
  total_eligible_sessions: number; present: number; late: number; absent: number; excused: number;
  attended: number; percentage: number | null; below_threshold: boolean;
}
interface StudentDashboardData {
  profile: { student_number: string; full_name: string; department: string };
  courses: CourseSummary[]; overall_percentage: number | null; eligible_sessions: number; attended_sessions: number;
  face_enrolled: boolean; eligible_sessions_now: Array<{id:string;course_name:string;course_code:string;title:string;starts_at:string;ends_at:string;location_name:string}>;
  recent_attendance: Array<{id:string;course_code:string;course_name:string;status:string;marked_at:string;title:string}>;
  unread_notifications:number; attendance_threshold:number;
}

export function StudentDashboard() {
  const query = useQuery({ queryKey: ['student-dashboard'], queryFn: () => api<StudentDashboardData>('/student/dashboard') });
  if (query.isLoading) return <Loading label="Loading your attendance overview…" />;
  if (query.error) return <PageError message="Your dashboard could not be loaded. Please refresh or sign in again." />;
  const data = query.data!;
  const chart = data.courses.filter((item) => item.percentage !== null).map((item) => ({
    course: item.course_code, attendance: item.percentage, threshold: item.threshold,
  }));
  return <main>
    <PageHeader eyebrow="STUDENT WORKSPACE" title={`Good day, ${data.profile.full_name.split(' ')[0]}`} description={`${data.profile.student_number} · Your attendance and course activity at a glance.`}
      actions={<Link to="/student/mark" className="button button-primary"><ClipboardCheck size={17} /> Mark attendance</Link>} />
    {!data.face_enrolled && <Notice kind="info">Before your first attendance check, enroll a face template from <Link to="/student/profile">your profile</Link>. Enrollment needs camera access and explicit consent.</Notice>}
    <div className="stats-grid">
      <StatCard label="Overall attendance" value={formatPercent(data.overall_percentage)} subtext={data.eligible_sessions ? `${data.attended_sessions} of ${data.eligible_sessions} eligible sessions` : 'No completed classes yet'} icon={<ChartIcon />} accent="blue" />
      <StatCard label="Enrolled courses" value={data.courses.length} subtext="Active course enrollments" icon={<BookOpen size={18} />} accent="purple" />
      <StatCard label="Open right now" value={data.eligible_sessions_now.length} subtext="Scheduled attendance windows" icon={<Clock3 size={18} />} accent="green" />
      <StatCard label="Unread updates" value={data.unread_notifications} subtext="In-app notifications" icon={<Sparkles size={18} />} accent="amber" />
    </div>
    <div className="dashboard-grid">
      <Card className="chart-card">
        <div className="card-heading"><div><span className="eyebrow">COURSE HEALTH</span><h2>Attendance by course</h2></div><span className="chart-key"><i /> Attendance <i className="key-threshold" /> Required</span></div>
        {chart.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height="260"><BarChart data={chart} margin={{ top: 12, right: 6, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9edf3" />
          <XAxis dataKey="course" axisLine={false} tickLine={false} tick={{ fill: '#6d7b8d', fontSize: 12 }} />
          <YAxis domain={[0, 100]} axisLine={false} tickLine={false} tick={{ fill: '#8b96a5', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
          <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Attendance']} contentStyle={{ border: '1px solid #e6eaf0', borderRadius: 12, boxShadow: '0 8px 22px #17304a12' }} />
          <Bar dataKey="attendance" fill="#1e7b69" radius={[6, 6, 0, 0]} maxBarSize={46} />
        </BarChart></ResponsiveContainer></div> : <EmptyState title="Your course chart is taking shape" message="Attendance percentages appear once at least one eligible class has ended." />}
        <p className="chart-footnote">Course thresholds are set by your institution. Excused and cancelled classes are excluded from the denominator.</p>
      </Card>
      <Card className="upcoming-card">
        <div className="card-heading"><div><span className="eyebrow">READY WHEN YOU ARE</span><h2>Attendance window</h2></div><span className="round-icon green-icon"><CalendarClock size={18} /></span></div>
        {data.eligible_sessions_now.length ? <div className="upcoming-list">{data.eligible_sessions_now.map((session) => <div className="upcoming-row" key={session.id}>
          <div className="upcoming-date"><span>{formatMonthDay(session.starts_at).month}</span><strong>{formatMonthDay(session.starts_at).day}</strong></div>
          <div className="upcoming-detail"><strong>{session.course_code} · {session.title}</strong><span>{session.course_name}</span><small><MapPin size={12} /> {session.location_name} · ends {formatDate(session.ends_at)}</small></div>
          <Link to={`/student/mark?session=${session.id}`} className="icon-button go-button" aria-label={`Start attendance for ${session.course_name}`}><ArrowRight size={16} /></Link>
        </div>)}</div> : <EmptyState title="No active attendance windows" message="Your scheduled classes will appear here during their attendance window." />}
      </Card>
    </div>
    <div className="dashboard-grid lower-grid">
      <Card><div className="card-heading"><div><span className="eyebrow">RECENT ACTIVITY</span><h2>Latest attendance</h2></div><Link className="text-link" to="/student/attendance">View history <ArrowRight size={14} /></Link></div>
        {data.recent_attendance.length ? <div className="table-wrap"><table><thead><tr><th>Course</th><th>Status</th><th>Recorded</th></tr></thead><tbody>
          {data.recent_attendance.map((row) => <tr key={row.id}><td><strong>{row.course_code}</strong><small className="cell-sub">{row.course_name}</small></td><td><Status value={row.status} /></td><td>{formatDate(row.marked_at)}</td></tr>)}
        </tbody></table></div> : <EmptyState title="No attendance history yet" message="Completed class records will appear here." />}
      </Card>
      <Card><div className="card-heading"><div><span className="eyebrow">COURSE SUMMARY</span><h2>Your courses</h2></div><BookOpen size={18} className="muted-icon" /></div>
        {data.courses.length ? <div className="course-list">{data.courses.map((course) => <Link to={`/student/attendance?course=${course.course_id}`} className="course-row" key={course.course_id}>
          <span className="course-mark">{course.course_code.slice(0, 2)}</span><span className="course-copy"><strong>{course.course_code}</strong><small>{course.course_name}</small></span>
          <span className={`course-percent ${course.below_threshold ? 'percent-warning' : ''}`}>{formatPercent(course.percentage)}<small>{course.attended}/{course.total_eligible_sessions}</small></span>
        </Link>)}</div> : <EmptyState title="No courses assigned" message="Ask your administrator to enroll you in your courses." />}
      </Card>
    </div>
  </main>;
}

export function TeacherDashboard() {
  const query = useQuery({ queryKey: ['teacher-dashboard'], queryFn: () => api<{assigned_courses:number;active_sessions:number;attendance_records:number;pending_corrections:number}>('/teacher/dashboard') });
  const courses = useQuery({ queryKey: ['teacher-courses'], queryFn: () => api<Array<{course_id:string;course_code:string;course_name:string;section_name:string}>>('/teacher/courses') });
  const watch = useQuery({ queryKey: ['teacher-watch'], queryFn: () => api<Array<{student_id:string;student_name:string;student_number:string;course_name:string;percentage:number;threshold:number}>>('/teacher/low-attendance') });
  if (query.isLoading) return <Loading label="Loading your teaching overview…" />;
  if (query.error) return <PageError message="Your teaching dashboard could not be loaded." />;
  const data = query.data!;
  return <main>
    <PageHeader eyebrow="TEACHER WORKSPACE" title="Classroom overview" description="Attendance and follow-up for the courses assigned to you."
      actions={<Link to="/teacher/classes" className="button button-primary"><CalendarClock size={17} /> View classes</Link>} />
    <div className="stats-grid">
      <StatCard label="Assigned courses" value={data.assigned_courses} subtext="Only your assigned sections" icon={<BookOpen size={18} />} accent="blue" />
      <StatCard label="Current sessions" value={data.active_sessions} subtext="Open or upcoming attendance" icon={<CalendarClock size={18} />} accent="green" />
      <StatCard label="Attendance records" value={data.attendance_records} subtext="Across authorized sessions" icon={<ClipboardCheck size={18} />} accent="purple" />
      <StatCard label="Pending reviews" value={data.pending_corrections} subtext="Student disputes and proposals" icon={<AlertTriangle size={18} />} accent="amber" />
    </div>
    <div className="dashboard-grid">
      <Card><div className="card-heading"><div><span className="eyebrow">MY TEACHING</span><h2>Assigned courses</h2></div><GraduationCap size={19} className="muted-icon" /></div>
        {courses.isLoading ? <Loading label="Loading courses…" /> : courses.data?.length ? <div className="course-list">{courses.data.map((course) => <Link key={`${course.course_id}-${course.section_name}`} to={`/teacher/classes?course=${course.course_id}`} className="course-row">
          <span className="course-mark purple-mark">{course.course_code.slice(0, 2)}</span><span className="course-copy"><strong>{course.course_code}</strong><small>{course.course_name} · {course.section_name}</small></span><ArrowRight size={16} className="muted-icon" />
        </Link>)}</div> : <EmptyState title="No courses assigned yet" message="Your administrator can assign you to courses and sections." />}
      </Card>
      <Card><div className="card-heading"><div><span className="eyebrow">STUDENT SUPPORT</span><h2>Attendance watch</h2></div><AlertTriangle size={18} className="warning-icon" /></div>
        {watch.data?.length ? <div className="watch-list">{watch.data.slice(0, 5).map((row) => <div className="watch-row" key={`${row.student_id}-${row.course_name}`}><span className="watch-avatar">{row.student_name.split(' ').map((s) => s[0]).slice(0,2).join('')}</span><span className="course-copy"><strong>{row.student_name}</strong><small>{row.student_number} · {row.course_name}</small></span><Badge tone="warning">{formatPercent(row.percentage)}</Badge></div>)}</div> : <EmptyState title="No low-attendance alerts" message="Students below their course threshold will be listed here." />}
        <Link to="/teacher/low-attendance" className="text-link card-bottom-link">Open attendance watch <ArrowRight size={14} /></Link>
      </Card>
    </div>
    {query.error && <Notice kind="error">Some dashboard data is temporarily unavailable.</Notice>}
  </main>;
}

export function AdminDashboard() {
  const query = useQuery({ queryKey: ['admin-dashboard'], queryFn: () => api<{students:number;teachers:number;courses:number;upcoming_sessions:number;pending_corrections:number;failed_verifications:number}>('/admin/dashboard') });
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<Record<string, any>>('/health/ready') });
  if (query.isLoading) return <Loading label="Loading campus overview…" />;
  if (query.error) return <PageError message="The administrator overview could not be loaded." />;
  const data = query.data!;
  return <main>
    <PageHeader eyebrow="ADMINISTRATOR WORKSPACE" title="Campus overview" description="A live view of your academic setup, account base and attendance activity."
      actions={<Link to="/admin/academics" className="button button-primary"><BookOpen size={17} /> Academic setup</Link>} />
    <div className="stats-grid">
      <StatCard label="Active students" value={data.students} subtext="Registered student records" icon={<GraduationCap size={18} />} accent="blue" />
      <StatCard label="Teachers" value={data.teachers} subtext="Managed teaching accounts" icon={<Users size={18} />} accent="purple" />
      <StatCard label="Active courses" value={data.courses} subtext="Available course catalog" icon={<BookOpen size={18} />} accent="green" />
      <StatCard label="Upcoming classes" value={data.upcoming_sessions} subtext="Not cancelled" icon={<CalendarClock size={18} />} accent="amber" />
    </div>
    <div className="dashboard-grid admin-grid">
      <Card className="quick-actions-card"><div className="card-heading"><div><span className="eyebrow">GET STARTED</span><h2>Manage campus operations</h2></div><Sparkles size={18} className="muted-icon" /></div>
        <div className="quick-action-grid">
          <Link to="/admin/people" className="quick-action"><span className="quick-icon blue-icon"><Users size={18} /></span><strong>Register a student</strong><small>Create an invitation and account</small><ArrowRight size={15} /></Link>
          <Link to="/admin/academics" className="quick-action"><span className="quick-icon purple-icon"><BookOpen size={18} /></span><strong>Set up courses</strong><small>Departments, courses and sections</small><ArrowRight size={15} /></Link>
          <Link to="/admin/locations" className="quick-action"><span className="quick-icon green-icon"><MapPin size={18} /></span><strong>Configure a classroom</strong><small>Geofence and class schedule</small><ArrowRight size={15} /></Link>
          <Link to="/admin/attendance" className="quick-action"><span className="quick-icon amber-icon"><ChartIcon /></span><strong>Review attendance</strong><small>Export an institutional report</small><ArrowRight size={15} /></Link>
        </div>
      </Card>
      <Card className="health-card"><div className="card-heading"><div><span className="eyebrow">SYSTEM STATUS</span><h2>Local services</h2></div><ActivityIcon /></div>
        {health.data ? <div className="health-list">
          <div><span><i className="status-dot status-green" /> Database</span><Badge tone="success">Connected</Badge></div>
          <div><span><i className={`status-dot ${health.data.vision_models?.ready ? 'status-green' : 'status-amber'}`} /> Face models</span><Badge tone={health.data.vision_models?.ready ? 'success' : 'warning'}>{health.data.vision_models?.ready ? 'Verified' : 'Needs setup'}</Badge></div>
          <div><span><i className={`status-dot ${health.data.vision_models?.biometric_storage_key_configured ? 'status-green' : 'status-red'}`} /> Biometric key</span><Badge tone={health.data.vision_models?.biometric_storage_key_configured ? 'success' : 'danger'}>{health.data.vision_models?.biometric_storage_key_configured ? 'Valid' : 'Unavailable'}</Badge></div>
          <div><span><i className="status-dot status-green" /> Campus timezone</span><small>{health.data.campus_timezone || 'UTC'}</small></div>
          <div><span><i className="status-dot status-green" /> Inference</span><small>Local CPU</small></div>
        </div> : health.isError ? <Notice kind="error">System readiness could not be checked. Review the API and database service.</Notice> : <div className="health-wait"><Loading label="Checking readiness…" /></div>}
        {health.data && !health.data.vision_models?.ready && <p className="health-note">Install and checksum the local face models before enabling biometric attendance. <Link to="/admin/system">View setup</Link></p>}
        <Link to="/admin/system" className="text-link card-bottom-link">View system health <ArrowRight size={14} /></Link>
      </Card>
    </div>
    {(data.pending_corrections > 0 || data.failed_verifications > 0) && <div className="attention-strip">
      <span className="attention-icon"><AlertTriangle size={18} /></span><span><strong>Items need your attention</strong><small>{data.pending_corrections} correction reviews · {data.failed_verifications} rejected verification attempts</small></span>
      <Link to="/admin/corrections" className="button button-secondary button-small">Review queue <ArrowRight size={14} /></Link>
    </div>}
  </main>;
}

function ChartIcon() { return <Activity size={18} />; }
function ActivityIcon() { return <Activity size={18} className="muted-icon" />; }
function Status({ value }: { value: string }) { return <Badge tone={value === 'present' ? 'success' : value === 'late' ? 'warning' : value === 'excused' ? 'info' : 'danger'}>{value}</Badge>; }
function PageError({ message }: { message: string }) { return <div className="page-error"><Notice kind="error">{message}</Notice><button className="button button-secondary" onClick={() => window.location.reload()}>Retry</button></div>; }
