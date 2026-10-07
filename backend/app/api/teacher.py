import csv
from datetime import timedelta
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.api.admin import CorrectionDecision, correction_view
from app.core.timezone import CampusRangeEnd, CampusRangeStart, as_utc, campus_date, to_campus, utc_now
from app.db.session import get_db
from app.models.entities import (
    Attendance,
    ClassSession,
    Course,
    CorrectionRequest,
    Enrollment,
    Section,
    Student,
    Teacher,
    TeacherAssignment,
    User,
)
from app.services.corrections import resolve_correction
from app.services.metrics import course_attendance_summary

router = APIRouter(prefix="/teacher", tags=["teacher"])
teacher_only = require_roles("teacher")


class CorrectionProposal(BaseModel):
    student_id: str
    session_id: str
    requested_status: str
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("requested_status")
    @classmethod
    def status_allowed(cls, value: str):
        if value not in {"present", "late", "absent", "excused"}:
            raise ValueError("Status must be present, late, absent, or excused")
        return value


@router.get("/dashboard")
def dashboard(user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    if not teacher:
        raise HTTPException(403, "Teacher profile is unavailable")
    assignments = _assignments(db, teacher.id)
    course_ids = {a.course_id for a in assignments}
    sessions = db.query(ClassSession).filter(ClassSession.course_id.in_(course_ids)).all() if course_ids else []
    active_sessions = [s for s in sessions if not s.cancelled and as_utc(s.ends_at) + timedelta(minutes=s.grace_minutes) >= utc_now()]
    attendance_count = db.query(Attendance).filter(Attendance.session_id.in_([s.id for s in sessions])).count() if sessions else 0
    pending = db.query(CorrectionRequest).filter(CorrectionRequest.status == "pending").all()
    pending = [item for item in pending if _session_is_assigned(db, teacher.id, db.get(ClassSession, item.session_id))]
    return {"assigned_courses": len(course_ids), "active_sessions": len(active_sessions),
            "attendance_records": attendance_count, "pending_corrections": len(pending)}


@router.get("/courses")
def assigned_courses(user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    if not teacher:
        raise HTTPException(403, "Teacher profile is unavailable")
    unique: dict[str, dict] = {}
    for assignment in _assignments(db, teacher.id):
        course = db.get(Course, assignment.course_id)
        section = db.get(Section, assignment.section_id) if assignment.section_id else None
        if not course:
            continue
        unique[f"{course.id}:{assignment.section_id or '*'}"] = {
            "course_id": course.id, "course_code": course.course_code, "course_name": course.name,
            "department_id": course.department_id, "section_id": assignment.section_id,
            "section_name": section.name if section else "All sections",
            "attendance_threshold": course.attendance_threshold,
        }
    return list(unique.values())


@router.get("/sessions")
def assigned_sessions(course_id: str | None = None, from_date: CampusRangeStart | None = None,
                    to_date: CampusRangeEnd | None = None,
                    limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                    user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    if not teacher:
        raise HTTPException(403, "Teacher profile is unavailable")
    ids = {a.course_id for a in _assignments(db, teacher.id)}
    if course_id and course_id not in ids:
        raise HTTPException(403, "This course is not assigned to you")
    query = db.query(ClassSession).filter(ClassSession.course_id.in_(ids)) if ids else db.query(ClassSession).filter(False)
    if from_date:
        query = query.filter(ClassSession.starts_at >= from_date)
    if to_date:
        # Exclusive bound: a bare date covers the whole campus day, so 23:59 IST is still included.
        query = query.filter(ClassSession.starts_at < to_date)
    rows = query.order_by(ClassSession.starts_at.desc()).all()
    rows = [row for row in rows if _session_is_assigned(db, teacher.id, row)]
    total = len(rows)
    rows = rows[offset:offset + limit]
    return {"items": [_session_view(db, row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/sessions/{session_id}/register")
def session_register(session_id: str, user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    session = db.get(ClassSession, session_id)
    if not teacher or not session or not _session_is_assigned(db, teacher.id, session):
        raise HTTPException(404, "Assigned class session not found")
    query = db.query(Enrollment, Student, User).join(Student, Student.id == Enrollment.student_id)
    query = query.join(User, User.id == Student.user_id).filter(
        Enrollment.course_id == session.course_id, Enrollment.active.is_(True)
    )
    if session.section_id:
        query = query.filter(Enrollment.section_id == session.section_id)
    records = {row.student_id: row for row in db.query(Attendance).filter(Attendance.session_id == session.id).all()}
    ended = as_utc(session.ends_at) + timedelta(minutes=session.grace_minutes) < utc_now()
    items = []
    for enrollment, student, student_user in query.order_by(Student.student_number).all():
        record = records.get(student.id)
        summary = course_attendance_summary(db, student, db.get(Course, session.course_id))
        items.append({"student_id": student.id, "student_number": student.student_number,
                      "student_name": student_user.full_name, "attendance_status": record.status if record else ("absent" if ended else "pending"),
                      "marked_at": to_campus(record.marked_at) if record else None,
                      "marked_on_ist": campus_date(record.marked_at) if record else None,
                      "attendance_percentage": summary["percentage"],
                      "eligible_sessions": summary["total_eligible_sessions"]})
    return {"session": _session_view(db, session), "students": items, "total": len(items)}


@router.get("/low-attendance")
def low_attendance(course_id: str | None = None, user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    if not teacher:
        raise HTTPException(403, "Teacher profile is unavailable")
    assignments = _assignments(db, teacher.id)
    assigned = {assignment.course_id for assignment in assignments}
    if course_id and course_id not in assigned:
        raise HTTPException(403, "This course is not assigned to you")
    chosen = {course_id} if course_id else assigned
    result = []
    for assignment in assignments:
        if assignment.course_id not in chosen:
            continue
        course = db.get(Course, assignment.course_id)
        query = db.query(Enrollment, Student, User).join(Student, Student.id == Enrollment.student_id)
        query = query.join(User, User.id == Student.user_id).filter(
            Enrollment.course_id == course.id, Enrollment.active.is_(True), User.active.is_(True)
        )
        if assignment.section_id:
            query = query.filter(Enrollment.section_id == assignment.section_id)
        for _, student, student_user in query.all():
            summary = course_attendance_summary(db, student, course)
            if summary["below_threshold"]:
                result.append({"student_id": student.id, "student_number": student.student_number,
                               "student_name": student_user.full_name, **summary})
    unique = {(item["student_id"], item["course_id"]): item for item in result}
    return list(unique.values())


@router.get("/corrections")
def corrections(status_filter: str = Query("pending", alias="status"),
               user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    if not teacher:
        raise HTTPException(403, "Teacher profile is unavailable")
    rows = db.query(CorrectionRequest).filter(CorrectionRequest.status == status_filter).order_by(
        CorrectionRequest.created_at.desc()).limit(300).all()
    return [correction_view(db, row) for row in rows
            if _session_is_assigned(db, teacher.id, db.get(ClassSession, row.session_id))]


@router.post("/corrections", status_code=201)
def propose_correction(payload: CorrectionProposal, user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    session = db.get(ClassSession, payload.session_id)
    student = db.get(Student, payload.student_id)
    if not teacher or not session or not student or not _session_is_assigned(db, teacher.id, session):
        raise HTTPException(404, "Assigned session or student not found")
    if not db.query(Enrollment).filter(Enrollment.student_id == student.id, Enrollment.course_id == session.course_id,
                                      Enrollment.active.is_(True)).first():
        raise HTTPException(422, "Student is not enrolled in this course")
    item = CorrectionRequest(student_id=student.id, session_id=session.id,
                             requested_status=payload.requested_status, reason=payload.reason.strip(),
                             submitted_by=user.id)
    db.add(item)
    db.commit()
    return {"id": item.id, "status": item.status, "requested_status": item.requested_status}


@router.post("/corrections/{request_id}/resolve")
def resolve_teacher_correction(request_id: str, payload: CorrectionDecision,
                               user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    item = db.get(CorrectionRequest, request_id)
    session = db.get(ClassSession, item.session_id) if item else None
    if not teacher or not item or not session or not _session_is_assigned(db, teacher.id, session):
        raise HTTPException(404, "Assigned correction request not found")
    return resolve_correction(db, item, user, payload.approved, payload.decision_reason)


@router.get("/export.csv")
def export_csv(course_id: str | None = None, session_id: str | None = None,
              user: User = Depends(teacher_only), db: Session = Depends(get_db)):
    teacher = _teacher_for_user(db, user)
    if not teacher:
        raise HTTPException(403, "Teacher profile is unavailable")
    assigned = {a.course_id for a in _assignments(db, teacher.id)}
    if course_id and course_id not in assigned:
        raise HTTPException(403, "This course is not assigned to you")
    query = db.query(Attendance, Student, User, ClassSession, Course).join(
        Student, Student.id == Attendance.student_id).join(User, User.id == Student.user_id).join(
        ClassSession, ClassSession.id == Attendance.session_id).join(Course, Course.id == ClassSession.course_id)
    query = query.filter(Course.id.in_(assigned)) if assigned else query.filter(False)
    if course_id:
        query = query.filter(Course.id == course_id)
    if session_id:
        query = query.filter(ClassSession.id == session_id)
    rows = [row for row in query.order_by(Attendance.marked_at.desc()).all()
            if _session_is_assigned(db, teacher.id, row[3])]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["student_number", "student_name", "course_code", "course_name", "session_id", "status",
                     "marked_on_ist", "marked_at_ist"])
    for attendance, student, student_user, session, course in rows:
        writer.writerow([_csv_safe(student.student_number), _csv_safe(student_user.full_name), _csv_safe(course.course_code),
                         _csv_safe(course.name), session.id, attendance.status,
                         campus_date(attendance.marked_at).isoformat(),
                         to_campus(attendance.marked_at).isoformat()])
    stream.seek(0)
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=ssams-teacher-attendance.csv"})


def _teacher_for_user(db: Session, user: User) -> Teacher | None:
    return db.query(Teacher).filter(Teacher.user_id == user.id).first()


def _assignments(db: Session, teacher_id: str):
    return db.query(TeacherAssignment).filter(TeacherAssignment.teacher_id == teacher_id).all()


def _session_is_assigned(db: Session, teacher_id: str, session: ClassSession | None) -> bool:
    if not session:
        return False
    assignments = db.query(TeacherAssignment).filter(
        TeacherAssignment.teacher_id == teacher_id,
        TeacherAssignment.course_id == session.course_id,
    ).all()
    return any(a.section_id is None or a.section_id == session.section_id for a in assignments)


def _session_view(db: Session, session: ClassSession) -> dict:
    course = db.get(Course, session.course_id)
    section = db.get(Section, session.section_id) if session.section_id else None
    return {"id": session.id, "course_id": session.course_id, "course_code": course.course_code if course else None,
            "course_name": course.name if course else None, "section_id": session.section_id,
            "section_name": section.name if section else "All sections", "title": session.title,
            "starts_at": to_campus(session.starts_at), "ends_at": to_campus(session.ends_at),
            "starts_on_ist": campus_date(session.starts_at), "grace_minutes": session.grace_minutes,
            "cancelled": session.cancelled}


def _csv_safe(value: str) -> str:
    value = str(value or "")
    first_nonspace = value.lstrip(" \t\r\n")[:1]
    dangerous = value[:1] in {"\t", "\r", "\n"} or first_nonspace in {"=", "+", "-", "@"}
    return "'" + value if dangerous else value
