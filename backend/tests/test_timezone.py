"""Timezone guarantees: the application runs on Asia/Kolkata (IST, UTC+05:30).

These tests pin the behaviour that matters operationally:

* storage stays on UTC instants;
* every API/CSV/HTML timestamp is expressed in IST;
* attendance date filters use IST midnight, so a record marked at 23:59 IST belongs to that Indian
  calendar day even though the server clock (UTC) has not crossed midnight yet.
"""
from datetime import date, datetime, timedelta, timezone

from app.core.config import settings
from app.core.timezone import (
    campus_date,
    campus_day_bounds,
    campus_now,
    campus_timezone_name,
    range_end,
    range_start,
    to_campus,
    utc_offset_label,
)
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.entities import (
    Attendance,
    ClassSession,
    Course,
    Department,
    Enrollment,
    Location,
    Student,
    Teacher,
    TeacherAssignment,
    User,
)
from tests.conftest import login

IST = timezone(timedelta(hours=5, minutes=30))


def test_application_timezone_is_india_standard_time():
    assert campus_timezone_name() == "Asia/Kolkata"
    assert settings.campus_timezone == "Asia/Kolkata"
    assert utc_offset_label() == "+05:30"
    assert campus_now().utcoffset() == timedelta(hours=5, minutes=30)


def test_utc_instants_render_as_ist_iso8601():
    instant = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    assert to_campus(instant).isoformat() == "2026-10-07T20:30:00+05:30"
    # A naive value is a stored UTC instant (SQLite returns naive datetimes).
    assert to_campus(datetime(2026, 10, 7, 15, 0)).isoformat() == "2026-10-07T20:30:00+05:30"


def test_campus_day_boundaries_use_ist_midnight():
    start, end = campus_day_bounds(date(2026, 10, 7))
    assert start == datetime(2026, 10, 6, 18, 30, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 7, 18, 30, tzinfo=timezone.utc)
    # Filter aliases: a bare date means the whole campus day.
    assert range_start(datetime(2026, 10, 7)) == datetime(2026, 10, 6, 18, 30, tzinfo=timezone.utc)
    assert range_end(datetime(2026, 10, 7)) == datetime(2026, 10, 7, 18, 30, tzinfo=timezone.utc)
    # An explicit instant is respected as-is.
    assert range_end(datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)) == datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def test_midnight_rollover_uses_the_indian_calendar_date():
    # 2026-10-07 19:00 UTC is still 7 October in UTC but already 00:30 IST on 8 October.
    after_ist_midnight = datetime(2026, 10, 7, 19, 0, tzinfo=timezone.utc)
    assert after_ist_midnight.date() == date(2026, 10, 7)
    assert campus_date(after_ist_midnight) == date(2026, 10, 8)
    # 2026-10-07 18:29 UTC == 23:59 IST still belongs to 7 October.
    assert campus_date(datetime(2026, 10, 7, 18, 29, tzinfo=timezone.utc)) == date(2026, 10, 7)
    assert campus_date(datetime(2026, 10, 7, 18, 31, tzinfo=timezone.utc)) == date(2026, 10, 8)


def test_health_endpoints_report_the_indian_timezone(client):
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json()["campus_timezone"] == "Asia/Kolkata"
    assert live.json()["campus_utc_offset"] == "+05:30"

    alias = client.get("/api/health")
    assert alias.status_code == 200
    assert alias.json()["status"] == "ok"
    assert alias.json()["campus_timezone"] == "Asia/Kolkata"
    assert alias.json()["server_time_local"].endswith("+05:30")

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["campus_timezone"] == "Asia/Kolkata"
    assert ready.json()["campus_utc_offset"] == "+05:30"


def test_attendance_api_returns_ist_timestamps(client, make_user):
    admin = make_user("admin", "ist-admin@example.com")
    late_evening = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)  # 20:30 IST
    with SessionLocal() as db:
        _, _, student, _, _, _, class_session = _class_fixture(db, admin, "TZ1")
        class_session.starts_at = datetime(2026, 10, 7, 14, 30, tzinfo=timezone.utc)
        class_session.ends_at = datetime(2026, 10, 7, 15, 30, tzinfo=timezone.utc)
        db.add(Attendance(student_id=student.id, session_id=class_session.id, status="present", marked_at=late_evening))
        db.commit()
    login(client, "ist-admin@example.com")

    response = client.get("/api/v1/admin/attendance")
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["marked_at"] == "2026-10-07T20:30:00+05:30"
    assert item["marked_on_ist"] == "2026-10-07"

    sessions = client.get("/api/v1/admin/sessions")
    assert sessions.status_code == 200, sessions.text
    starts_at = sessions.json()["items"][0]["starts_at"]
    assert starts_at == "2026-10-07T20:00:00+05:30", starts_at


def test_attendance_date_filters_use_ist_midnight(client, make_user):
    admin = make_user("admin", "ist-filter@example.com")
    with SessionLocal() as db:
        _, _, student, _, course, _, class_session = _class_fixture(db, admin, "TZ2")
        other_user = User(email="ist-filter-second@example.com", full_name="Second Student", role="student",
                          active=True, password_hash="x" * 20)
        db.add(other_user)
        db.flush()
        other = Student(user_id=other_user.id, student_number="TZ2-B", department_id=student.department_id)
        db.add(other)
        db.flush()
        db.add(Enrollment(student_id=other.id, course_id=course.id, active=True))
        # 18:00 UTC == 23:30 IST on 7 October; 19:00 UTC == 00:30 IST on 8 October.
        db.add_all([
            Attendance(student_id=student.id, session_id=class_session.id, status="present",
                       marked_at=datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)),
            Attendance(student_id=other.id, session_id=class_session.id, status="late",
                       marked_at=datetime(2026, 10, 7, 19, 0, tzinfo=timezone.utc)),
        ])
        db.commit()
        first_id, second_id = student.id, other.id
    login(client, "ist-filter@example.com")

    seventh = client.get("/api/v1/admin/attendance?start=2026-10-07&end=2026-10-07")
    assert seventh.status_code == 200, seventh.text
    assert [row["student_id"] for row in seventh.json()["items"]] == [first_id]
    assert seventh.json()["items"][0]["marked_at"] == "2026-10-07T23:30:00+05:30"

    eighth = client.get("/api/v1/admin/attendance?start=2026-10-08&end=2026-10-08")
    assert eighth.status_code == 200, eighth.text
    assert [row["student_id"] for row in eighth.json()["items"]] == [second_id]
    assert eighth.json()["items"][0]["marked_on_ist"] == "2026-10-08"


def test_reports_export_ist(client, make_user):
    admin = make_user("admin", "ist-report@example.com")
    with SessionLocal() as db:
        _, _, student, _, _, _, class_session = _class_fixture(db, admin, "TZ3")
        db.add(Attendance(student_id=student.id, session_id=class_session.id, status="present",
                          marked_at=datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)))
        db.commit()
    login(client, "ist-report@example.com")

    csv_export = client.get("/api/v1/admin/reports/attendance.csv")
    assert csv_export.status_code == 200, csv_export.text
    assert "marked_on_ist" in csv_export.text and "marked_at_ist" in csv_export.text
    assert "2026-10-07T20:30:00+05:30" in csv_export.text
    assert "marked_at_utc" not in csv_export.text

    printable = client.get("/api/v1/admin/reports/print")
    assert printable.status_code == 200, printable.text
    assert "Recorded at (IST)" in printable.text
    assert "2026-10-07 20:30 IST" in printable.text
    assert "Asia/Kolkata" in printable.text


def test_teacher_session_filters_use_ist_midnight(client, make_user):
    admin = make_user("admin", "ist-teacher@example.com")
    with SessionLocal() as db:
        _, teacher_user, _, _, course, location, class_session = _class_fixture(db, admin, "TZ4")
        db.add(ClassSession(course_id=course.id, location_id=location.id, title="After IST midnight",
                            starts_at=datetime(2026, 10, 7, 19, 0, tzinfo=timezone.utc),
                            ends_at=datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc),
                            grace_minutes=10, created_by=admin.id))
        db.commit()
        teacher_email = teacher_user.email
    login(client, teacher_email)

    seventh = client.get("/api/v1/teacher/sessions?from_date=2026-10-07&to_date=2026-10-07")
    assert seventh.status_code == 200, seventh.text
    assert [row["starts_on_ist"] for row in seventh.json()["items"]] == ["2026-10-07"]
    assert seventh.json()["items"][0]["starts_at"] == "2026-10-07T20:30:00+05:30"

    eighth = client.get("/api/v1/teacher/sessions?from_date=2026-10-08&to_date=2026-10-08")
    assert eighth.status_code == 200, eighth.text
    assert [row["starts_on_ist"] for row in eighth.json()["items"]] == ["2026-10-08"]


def _class_fixture(db, user: User, suffix: str):
    """Minimal department/course/location/student/teacher/session graph for a test."""
    department = Department(name=f"Department {suffix}", code=f"D{suffix}")
    db.add(department)
    db.flush()
    course = Course(department_id=department.id, course_code=f"C{suffix}", name=f"Course {suffix}",
                    attendance_threshold=75)
    location = Location(department_id=department.id, name=f"Room {suffix}", latitude=51.5, longitude=-0.12,
                        radius_m=300, max_accuracy_m=75)
    db.add_all([course, location])
    db.flush()
    student_user = User(email=f"s-{suffix.lower()}@example.com", full_name=f"Student {suffix}", role="student",
                        active=True, password_hash=hash_password("TestPass12345"))
    teacher_user = User(email=f"t-{suffix.lower()}@example.com", full_name=f"Teacher {suffix}", role="teacher",
                        active=True, password_hash=hash_password("TestPass12345"))
    db.add_all([student_user, teacher_user])
    db.flush()
    student = Student(user_id=student_user.id, student_number=f"ID-{suffix}", department_id=department.id)
    teacher = Teacher(user_id=teacher_user.id, employee_number=f"EMP-{suffix}", department_id=department.id)
    db.add_all([student, teacher])
    db.flush()
    db.add_all([Enrollment(student_id=student.id, course_id=course.id, active=True),
                TeacherAssignment(teacher_id=teacher.id, course_id=course.id)])
    class_session = ClassSession(course_id=course.id, location_id=location.id, title="IST class",
                                 starts_at=datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc),
                                 ends_at=datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc),
                                 grace_minutes=10, created_by=user.id)
    db.add(class_session)
    db.commit()
    return student_user, teacher_user, student, teacher, course, location, class_session
