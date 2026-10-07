import csv
import html
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.core.config import settings
from app.core.timezone import CampusRangeEnd, CampusRangeStart, campus_date, campus_now, to_campus
from app.db.session import get_db
from app.models.entities import Attendance, ClassSession, Course, Enrollment, Student, User

router = APIRouter(prefix="/reports", tags=["reports"])
admin_router = APIRouter(prefix="/admin/reports", tags=["reports"])
admin_only = require_roles("admin")
student_only = require_roles("student")


@router.get("/attendance.csv")
def student_attendance_csv(user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.user_id == user.id).first()
    rows = []
    if student:
        rows = (db.query(Attendance, ClassSession, Course)
                .join(ClassSession, ClassSession.id == Attendance.session_id)
                .join(Course, Course.id == ClassSession.course_id)
                .join(Enrollment, Enrollment.course_id == Course.id)
                .filter(Attendance.student_id == student.id, Enrollment.student_id == student.id)
                .order_by(Attendance.marked_at.desc()).all())
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["course_code", "course_name", "class_title", "status", "marked_on_ist", "marked_at_ist"])
    for attendance, session, course in rows:
        writer.writerow([_safe_csv(course.course_code), _safe_csv(course.name), _safe_csv(session.title), attendance.status,
                         campus_date(attendance.marked_at).isoformat(),
                         to_campus(attendance.marked_at).isoformat()])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=my-ssams-attendance.csv"})


@admin_router.get("/attendance.csv")
def admin_attendance_csv(
    course_id: str | None = None,
    start: CampusRangeStart | None = None,
    end: CampusRangeEnd | None = None,
    status_filter: Literal["present", "late", "absent", "excused"] | None = Query(None, alias="status"),
    limit: int = Query(5000, ge=1, le=20000),
    _: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    rows = _admin_query(db, course_id, start, end, status_filter).order_by(Attendance.marked_at.desc()).limit(limit).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["student_number", "student_name", "email", "course_code", "course_name", "session_id",
                     "status", "marked_on_ist", "marked_at_ist", "correction_reason"])
    for attendance, student, student_user, session, course in rows:
        writer.writerow([_safe_csv(student.student_number), _safe_csv(student_user.full_name),
                         _safe_csv(student_user.email), _safe_csv(course.course_code), _safe_csv(course.name), session.id,
                         attendance.status, campus_date(attendance.marked_at).isoformat(),
                         to_campus(attendance.marked_at).isoformat(),
                         _safe_csv(attendance.correction_reason or "")])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=ssams-attendance.csv"})


@admin_router.get("/print", response_class=HTMLResponse)
def admin_print_report(course_id: str | None = None, start: CampusRangeStart | None = None,
                       end: CampusRangeEnd | None = None,
                       status_filter: Literal["present", "late", "absent", "excused"] | None = Query(None, alias="status"),
                       _: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = _admin_query(db, course_id, start, end, status_filter).order_by(Attendance.marked_at.desc()).limit(2000).all()
    body = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(student.student_number), html.escape(student_user.full_name),
            html.escape(course.course_code), html.escape(course.name), html.escape(attendance.status),
            html.escape(to_campus(attendance.marked_at).strftime("%Y-%m-%d %H:%M IST")),
        ) for attendance, student, student_user, session, course in rows
    )
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SSAMS attendance report</title>
    <style>body{{font:14px system-ui;margin:32px;color:#15243a}}h1{{color:#173766}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd4df;padding:8px;text-align:left}}th{{background:#edf3f9}}@media print{{button{{display:none}}}}</style>
    </head><body><h1>SSAMS attendance report</h1><p>Generated {campus_now().strftime('%Y-%m-%d %H:%M')} {settings.campus_timezone} · {len(rows)} records</p>
    <button onclick="window.print()">Print report</button><table><thead><tr><th>Student ID</th><th>Student</th><th>Course</th><th>Course name</th><th>Status</th><th>Recorded at (IST)</th></tr></thead><tbody>{body}</tbody></table></body></html>""")


def _admin_query(db: Session, course_id: str | None, start: datetime | None, end: datetime | None,
                 status_filter: str | None = None):
    # `start`/`end` arrive already normalised to UTC instants by CampusRangeStart/CampusRangeEnd.
    query = (db.query(Attendance, Student, User, ClassSession, Course)
             .join(Student, Student.id == Attendance.student_id)
             .join(User, User.id == Student.user_id)
             .join(ClassSession, ClassSession.id == Attendance.session_id)
             .join(Course, Course.id == ClassSession.course_id))
    if course_id:
        query = query.filter(Course.id == course_id)
    if start:
        query = query.filter(Attendance.marked_at >= start)
    if end:
        # Exclusive campus-time bound: `end=YYYY-MM-DD` includes the whole campus day (23:59 IST).
        query = query.filter(Attendance.marked_at < end)
    if status_filter:
        query = query.filter(Attendance.status == status_filter)
    return query


def _safe_csv(value: str) -> str:
    value = str(value or "")
    first_nonspace = value.lstrip(" \t\r\n")[:1]
    dangerous = value[:1] in {"\t", "\r", "\n"} or first_nonspace in {"=", "+", "-", "@"}
    return "'" + value if dangerous else value
