from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.timezone import as_utc, utc_now
from app.models.entities import Attendance, ClassSession, Course, Enrollment, Student


def course_attendance_summary(db: Session, student: Student, course: Course, now: datetime | None = None) -> dict:
    now = as_utc(now or utc_now())
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == student.id, Enrollment.course_id == course.id, Enrollment.active.is_(True))
        .first()
    )
    if not enrollment:
        return _empty_summary(course)
    section_filter = ClassSession.section_id.is_(None)
    if enrollment.section_id:
        section_filter = or_(ClassSession.section_id.is_(None), ClassSession.section_id == enrollment.section_id)
    sessions = (
        db.query(ClassSession)
        .filter(ClassSession.course_id == course.id, section_filter, ClassSession.cancelled.is_(False))
        .all()
    )
    ended = [session for session in sessions if as_utc(session.ends_at) + timedelta(minutes=session.grace_minutes) <= now]
    attendance = {
        record.session_id: record
        for record in db.query(Attendance).filter(
            Attendance.student_id == student.id,
            Attendance.session_id.in_([session.id for session in ended]),
        ).all()
    } if ended else {}
    counts = {"present": 0, "late": 0, "absent": 0, "excused": 0}
    for session in ended:
        record = attendance.get(session.id)
        state = record.status if record and record.status in counts else "absent"
        counts[state] += 1
    denominator = len(ended) - counts["excused"]
    attended = counts["present"] + counts["late"]
    percentage = (attended * 100.0 / denominator) if denominator else None
    return {
        "course_id": course.id,
        "course_code": course.course_code,
        "course_name": course.name,
        "threshold": course.attendance_threshold,
        "total_eligible_sessions": denominator,
        "scheduled_sessions": len(ended),
        "present": counts["present"],
        "late": counts["late"],
        "absent": counts["absent"],
        "excused": counts["excused"],
        "attended": attended,
        "percentage": round(percentage, 2) if percentage is not None else None,
        "below_threshold": percentage is not None and percentage < course.attendance_threshold,
    }


def student_summaries(db: Session, student: Student, now: datetime | None = None) -> list[dict]:
    enrollments = (
        db.query(Enrollment, Course)
        .join(Course, Course.id == Enrollment.course_id)
        .filter(Enrollment.student_id == student.id, Enrollment.active.is_(True), Course.active.is_(True))
        .all()
    )
    return [course_attendance_summary(db, student, course, now) for _, course in enrollments]


def _empty_summary(course: Course) -> dict:
    return {
        "course_id": course.id,
        "course_code": course.course_code,
        "course_name": course.name,
        "threshold": course.attendance_threshold,
        "total_eligible_sessions": 0,
        "scheduled_sessions": 0,
        "present": 0,
        "late": 0,
        "absent": 0,
        "excused": 0,
        "attended": 0,
        "percentage": None,
        "below_threshold": False,
    }
