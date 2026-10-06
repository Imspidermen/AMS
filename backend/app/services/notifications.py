from sqlalchemy.orm import Session

from app.models.entities import Notification, Student, User
from app.services.metrics import student_summaries


def generate_low_attendance_alerts(db: Session, student: Student, user: User, summaries: list[dict] | None = None) -> int:
    summaries = summaries if summaries is not None else student_summaries(db, student)
    created = 0
    for summary in summaries:
        percentage = summary["percentage"]
        if percentage is None or percentage >= summary["threshold"]:
            continue
        link = f"/student/attendance?course={summary['course_id']}"
        unread = db.query(Notification).filter(
            Notification.user_id == user.id,
            Notification.kind == "low_attendance",
            Notification.link == link,
            Notification.read_at.is_(None),
        ).first()
        if not unread:
            db.add(Notification(
                user_id=user.id,
                kind="low_attendance",
                title=f"Attendance below {summary['threshold']:.0f}%",
                message=(f"Your attendance in {summary['course_name']} is {percentage:.1f}%, below "
                         f"the required threshold of {summary['threshold']:.0f}%."),
                link=link,
            ))
            created += 1
    return created
