from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.config import settings
from app.core.security import utc_now
from app.db.session import get_db
from app.models.entities import (
    Attendance,
    ClassSession,
    Course,
    CorrectionRequest,
    Department,
    Enrollment,
    FaceEnrollment,
    Location,
    Notification,
    Student,
    User,
)
from app.services.metrics import student_summaries
from app.services.notifications import generate_low_attendance_alerts

router = APIRouter(prefix="/student", tags=["student"])
student_only = require_roles("student")


class StudentCorrectionInput(BaseModel):
    session_id: str
    requested_status: str = "present"
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("requested_status")
    @classmethod
    def validate_status(cls, value: str):
        if value not in {"present", "late", "excused"}:
            raise ValueError("A student may request present, late, or excused status")
        return value


@router.get("/profile")
def profile(user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = _profile(db, user)
    if not student:
        raise HTTPException(404, "Student profile not found")
    department = db.get(Department, student.department_id)
    face = db.query(FaceEnrollment).filter(FaceEnrollment.student_id == student.id).first()
    return {"id": student.id, "student_number": student.student_number, "full_name": user.full_name,
            "email": user.email, "department_id": student.department_id,
            "department_name": department.name if department else None, "program": student.program,
            "semester_id": student.semester_id, "enrollment_status": student.enrollment_status,
            "face_enrolled": face is not None, "face_enrolled_at": face.created_at if face else None,
            "account_active": user.active}


@router.get("/dashboard")
def dashboard(user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = _profile(db, user)
    if not student:
        raise HTTPException(404, "Student profile not found")
    summaries = student_summaries(db, student)
    generate_low_attendance_alerts(db, student, user, summaries)
    db.commit()
    total = sum(x["total_eligible_sessions"] for x in summaries)
    attended = sum(x["attended"] for x in summaries)
    enrollment = db.query(FaceEnrollment).filter(FaceEnrollment.student_id == student.id).first()
    now = utc_now()
    current = (
        db.query(ClassSession, Course, Location)
        .join(Course, Course.id == ClassSession.course_id)
        .join(Location, Location.id == ClassSession.location_id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .filter(Enrollment.student_id == student.id, Enrollment.active.is_(True),
                ClassSession.cancelled.is_(False), Course.active.is_(True), Location.active.is_(True),
                ClassSession.starts_at <= now)
        .order_by(ClassSession.starts_at)
        .all()
    )
    # SQLite cannot translate arithmetic on DateTime columns uniformly; filter the schedule in Python.
    eligible_now = []
    seen = set()
    for session, course, location in current:
        if session.id in seen or not _enrollment_matches(db, student.id, session):
            continue
        seen.add(session.id)
        if _as_utc(session.ends_at) + timedelta(minutes=session.grace_minutes) >= now:
            already = db.query(Attendance).filter(Attendance.student_id == student.id,
                                                  Attendance.session_id == session.id).first()
            if not already:
                eligible_now.append({"id": session.id, "course_code": course.course_code,
                                     "course_name": course.name, "title": session.title,
                                     "starts_at": session.starts_at, "ends_at": session.ends_at,
                                     "location_name": location.name})
    recent = (
        db.query(Attendance, ClassSession, Course)
        .join(ClassSession, ClassSession.id == Attendance.session_id)
        .join(Course, Course.id == ClassSession.course_id)
        .filter(Attendance.student_id == student.id)
        .order_by(Attendance.marked_at.desc()).limit(6).all()
    )
    notifications = db.query(Notification).filter(Notification.user_id == user.id,
                                                   Notification.read_at.is_(None)).count()
    return {"profile": {"student_number": student.student_number, "full_name": user.full_name,
                        "department": student.department_id},
            "courses": summaries,
            "overall_percentage": round(attended * 100.0 / total, 2) if total else None,
            "eligible_sessions": total, "attended_sessions": attended,
            "face_enrolled": enrollment is not None,
            "eligible_sessions_now": eligible_now,
            "recent_attendance": [{"id": record.id, "course_code": course.course_code,
                "course_name": course.name, "status": record.status, "marked_at": record.marked_at,
                "title": session.title} for record, session, course in recent],
            "unread_notifications": notifications,
            "attendance_threshold": min((x["threshold"] for x in summaries), default=settings.low_attendance_threshold)}


@router.get("/corrections")
def list_my_corrections(user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = _profile(db, user)
    if not student:
        return []
    rows = db.query(CorrectionRequest).filter(CorrectionRequest.student_id == student.id).order_by(
        CorrectionRequest.created_at.desc()).limit(100).all()
    result = []
    for item in rows:
        session = db.get(ClassSession, item.session_id)
        course = db.get(Course, session.course_id) if session else None
        result.append({"id": item.id, "session_id": item.session_id,
                       "course_name": course.name if course else None,
                       "requested_status": item.requested_status, "reason": item.reason,
                       "status": item.status, "decision_reason": item.decision_reason,
                       "created_at": item.created_at, "decided_at": item.decided_at})
    return result


@router.post("/corrections", status_code=201)
def request_correction(payload: StudentCorrectionInput, user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = _profile(db, user)
    session = db.get(ClassSession, payload.session_id)
    if not student or not session or session.cancelled or not _enrollment_matches(db, student.id, session):
        raise HTTPException(404, "Eligible class session not found")
    if _as_utc(session.ends_at) > utc_now():
        raise HTTPException(422, "Attendance disputes may be submitted after the class session ends")
    pending = db.query(CorrectionRequest).filter(
        CorrectionRequest.student_id == student.id,
        CorrectionRequest.session_id == session.id,
        CorrectionRequest.status == "pending",
    ).first()
    if pending:
        raise HTTPException(409, "A correction request is already pending for this session")
    item = CorrectionRequest(student_id=student.id, session_id=session.id,
                             requested_status=payload.requested_status, reason=payload.reason.strip(),
                             submitted_by=user.id)
    db.add(item)
    db.commit()
    return {"id": item.id, "status": item.status, "requested_status": item.requested_status,
            "message": "Your request has been sent for review."}


def _profile(db: Session, user: User) -> Student | None:
    return db.query(Student).filter(Student.user_id == user.id).first()


def _enrollment_matches(db: Session, student_id: str, session: ClassSession) -> bool:
    query = db.query(Enrollment).filter(Enrollment.student_id == student_id,
                                        Enrollment.course_id == session.course_id,
                                        Enrollment.active.is_(True))
    if session.section_id:
        query = query.filter(Enrollment.section_id == session.section_id)
    return query.first() is not None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
