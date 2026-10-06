from datetime import datetime, timedelta, timezone

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
    VerificationAttempt,
)
from tests.conftest import login


def test_untrusted_request_id_is_sanitized_and_consistent(client):
    response = client.get("/api/v1/student/profile", headers={"X-Request-ID": "untrusted id"})
    assert response.status_code == 401
    request_id = response.headers["X-Request-ID"]
    assert request_id != "untrusted id"
    assert response.json()["request_id"] == request_id
    assert len(request_id) <= 80
    assert all(character.isalnum() or character in "-_." for character in request_id)


def test_sqlite_model_datetimes_round_trip_as_utc_aware(client, make_user):
    admin = make_user("admin", "utc-roundtrip@example.com")
    with SessionLocal() as db:
        *_, session = _make_class_data(db, admin, "U")
        session_id = session.id
        db.expire_all()
        loaded = db.get(ClassSession, session_id)
        assert loaded.starts_at.tzinfo is not None
        assert loaded.starts_at.utcoffset() == timedelta(0)


def test_csrf_refresh_reuses_valid_session_token_with_sqlite_timestamps(client, make_user):
    make_user("student", "csrf-refresh@example.com")
    login(client, "csrf-refresh@example.com")
    original = client.cookies.get("ssams_csrf")
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200, response.text
    assert response.json()["csrf_token"] == original
    assert client.cookies.get("ssams_csrf") == original


def test_administrator_registration_activation_and_unique_ids(client, make_user):
    make_user("admin", "admin@example.com")
    login(client, "admin@example.com")
    department_response = client.post("/api/v1/admin/departments", json={"name": "Computing", "code": "CS"})
    assert department_response.status_code == 201, department_response.text
    department_id = department_response.json()["id"]
    created = client.post("/api/v1/admin/students", json={
        "email": "student@example.com", "full_name": "Student One", "student_number": "S-1001",
        "department_id": department_id, "program": "Computer Science",
    })
    assert created.status_code == 201, created.text
    invite = created.json()
    assert invite["activation_token"]
    duplicate = client.post("/api/v1/admin/students", json={
        "email": "another@example.com", "full_name": "Student Duplicate", "student_number": "S-1001",
        "department_id": department_id,
    })
    assert duplicate.status_code == 409
    activated = client.post("/api/v1/auth/activate", json={
        "token": invite["activation_token"], "password": "NewPassword12345",
    })
    assert activated.status_code == 200, activated.text
    student_client = client.__class__(client.app)
    student = login(student_client, "student@example.com", "NewPassword12345")
    assert student["role"] == "student"
    assert student["student_number"] == "S-1001"
    assert student_client.get("/api/v1/student/profile").status_code == 200


def test_role_access_and_csrf_are_enforced(client, make_user):
    make_user("student", "student@example.com")
    login(client, "student@example.com")
    forbidden = client.get("/api/v1/admin/departments")
    assert forbidden.status_code == 403
    csrf = client.headers.pop("X-CSRF-Token")
    mutation = client.post("/api/v1/student/corrections", json={
        "session_id": "untrusted", "requested_status": "present", "reason": "Incorrect attendance status",
    })
    assert mutation.status_code == 403
    client.headers["X-CSRF-Token"] = csrf


def _make_class_data(db, user: User, suffix: str = "A", start_offset_minutes: int = -5):
    department = Department(name=f"Department {suffix}", code=f"D{suffix}")
    db.add(department)
    db.flush()
    course = Course(department_id=department.id, course_code=f"C{suffix}101", name=f"Course {suffix}",
                    attendance_threshold=75)
    location = Location(department_id=department.id, name=f"Room {suffix}", latitude=51.5, longitude=-0.12,
                        radius_m=300, max_accuracy_m=75)
    db.add_all([course, location])
    db.flush()
    student_user = User(email=f"s{suffix.lower()}@example.com", full_name=f"Student {suffix}", role="student",
                        password_hash=hash_password("TestPass12345"), active=True)
    teacher_user = User(email=f"t{suffix.lower()}@example.com", full_name=f"Teacher {suffix}", role="teacher",
                        password_hash=hash_password("TestPass12345"), active=True)
    db.add_all([student_user, teacher_user])
    db.flush()
    student = Student(user_id=student_user.id, student_number=f"ID-{suffix}", department_id=department.id)
    teacher = Teacher(user_id=teacher_user.id, employee_number=f"EMP-{suffix}", department_id=department.id)
    db.add_all([student, teacher])
    db.flush()
    enrollment = Enrollment(student_id=student.id, course_id=course.id, active=True)
    assignment = TeacherAssignment(teacher_id=teacher.id, course_id=course.id)
    now = datetime.now(timezone.utc)
    session = ClassSession(course_id=course.id, location_id=location.id, title="Live class",
                           starts_at=now + timedelta(minutes=start_offset_minutes),
                           ends_at=now + timedelta(minutes=40), grace_minutes=10, created_by=user.id)
    db.add_all([enrollment, assignment, session])
    db.commit()
    return student_user, teacher_user, student, teacher, course, location, session


def test_teacher_is_limited_to_assigned_course_and_student_records(client, make_user):
    admin = make_user("admin", "admin@example.com")
    with SessionLocal() as db:
        student_user, _, student, _, course, location, session = _make_class_data(db, admin, "B")
        other_course = Course(department_id=course.department_id, course_code="OTHER1", name="Other course")
        db.add(other_course)
        db.commit()
        other_id = other_course.id
        session_id = session.id
    login(client, "tb@example.com")
    assigned = client.get("/api/v1/teacher/courses")
    assert assigned.status_code == 200
    assert [row["course_id"] for row in assigned.json()] == [course.id]
    assert client.get(f"/api/v1/teacher/sessions/{session_id}/register").status_code == 200
    assert client.get(f"/api/v1/teacher/sessions?course_id={other_id}").status_code == 403
    assert client.get("/api/v1/admin/departments").status_code == 403


def test_student_history_is_self_only(client, make_user):
    admin = make_user("admin", "admin@example.com")
    with SessionLocal() as db:
        s1_user, _, s1, _, course, _, session = _make_class_data(db, admin, "C")
        other_user = User(email="private@example.com", full_name="Private Person", role="student",
                          password_hash=hash_password("TestPass12345"), active=True)
        db.add(other_user)
        db.flush()
        other = Student(user_id=other_user.id, student_number="PRIVATE", department_id=s1.department_id)
        db.add(other)
        db.flush()
        db.add(Enrollment(student_id=other.id, course_id=course.id, active=True))
        db.add(Attendance(student_id=other.id, session_id=session.id, status="present", marked_at=datetime.now(timezone.utc)))
        db.commit()
        own_email = s1_user.email
    login(client, own_email)
    response = client.get("/api/v1/attendance/history")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert "PRIVATE" not in response.text


def test_server_side_geofence_rejects_outside_reading_and_records_attempt(client, make_user):
    admin = make_user("admin", "admin@example.com")
    with SessionLocal() as db:
        student_user, _, student, _, course, location, session = _make_class_data(db, admin, "G")
        session_id = session.id
        location.latitude = 0
        location.longitude = 0
        db.commit()
    login(client, student_user.email)
    now = datetime.now(timezone.utc).isoformat()
    response = client.post("/api/v1/attendance/attempts", json={
        "session_id": session_id, "latitude": 1, "longitude": 1, "accuracy_m": 5, "measured_at": now,
    })
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["message"] == "You are too far from the permitted classroom area to mark attendance."
    with SessionLocal() as db:
        record = db.query(VerificationAttempt).filter(VerificationAttempt.user_id == student_user.id).one()
        assert record.status == "rejected"
        assert record.reason == "outside_geofence"
        assert record.distance_m > 100_000


def test_valid_location_opens_random_challenge_bound_to_student(client, make_user):
    admin = make_user("admin", "admin@example.com")
    with SessionLocal() as db:
        student_user, _, student, _, course, location, session = _make_class_data(db, admin, "L")
        payload = {"session_id": session.id, "latitude": location.latitude, "longitude": location.longitude,
                   "accuracy_m": 8, "measured_at": datetime.now(timezone.utc).isoformat()}
    login(client, student_user.email)
    response = client.post("/api/v1/attendance/attempts", json=payload)
    assert response.status_code == 201, response.text
    challenge = response.json()
    assert set(challenge["actions"]) == {"blink", "return_neutral", "turn_left"} or set(challenge["actions"]) == {"blink", "return_neutral", "turn_right"}
    assert challenge["challenge_token"]
    assert challenge["expires_at"]
    assert client.post(f"/api/v1/attendance/challenges/{challenge['challenge_id']}/submit",
                       headers={"X-Liveness-Token": challenge["challenge_token"],
                                "Idempotency-Key": "x" * 24}, files={"frame": ("frame.jpg", b"bad", "image/jpeg")}).status_code == 409


def test_admin_correction_is_audited(client, make_user):
    admin = make_user("admin", "admin@example.com")
    with SessionLocal() as db:
        student_user, _, student, _, _, _, session = _make_class_data(db, admin, "M", start_offset_minutes=-180)
        session.ends_at = datetime.now(timezone.utc) - timedelta(minutes=90)
        session.starts_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()
        payload = {"student_id": student.id, "session_id": session.id, "status": "excused",
                   "reason": "Approved medical documentation"}
    login(client, "admin@example.com")
    response = client.post("/api/v1/admin/attendance/correct", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "excused"
    with SessionLocal() as db:
        record = db.query(Attendance).filter(Attendance.student_id == payload["student_id"]).one()
        assert record.status == "excused"
        from app.models.entities import AuditEvent
        audit = db.query(AuditEvent).filter(AuditEvent.action == "attendance.corrected").one()
        assert audit.details["reason"] == payload["reason"]


def test_admin_attendance_status_filter_returns_only_selected_status(client, make_user):
    admin = make_user("admin", "admin@example.com")
    with SessionLocal() as db:
        student_user, _, student, _, course, _, session = _make_class_data(db, admin, "F")
        student_user.full_name = " =1+1"
        course.course_code = "=2+2"
        other_user = User(email="filter@example.com", full_name="Filter Student", role="student",
                          password_hash=hash_password("TestPass12345"), active=True)
        db.add(other_user)
        db.flush()
        other = Student(user_id=other_user.id, student_number="ID-F2", department_id=student.department_id)
        db.add(other)
        db.flush()
        db.add_all([
            Enrollment(student_id=other.id, course_id=course.id, active=True),
            Attendance(student_id=student.id, session_id=session.id, status="present", marked_at=datetime.now(timezone.utc)),
            Attendance(student_id=other.id, session_id=session.id, status="absent", marked_at=datetime.now(timezone.utc)),
        ])
        db.commit()

    login(client, "admin@example.com")
    present = client.get("/api/v1/admin/attendance?status=present")
    absent = client.get("/api/v1/admin/attendance?status=absent")
    assert present.status_code == 200, present.text
    assert absent.status_code == 200, absent.text
    assert [row["status"] for row in present.json()["items"]] == ["present"]
    assert [row["status"] for row in absent.json()["items"]] == ["absent"]
    assert client.get("/api/v1/admin/attendance?status=unknown").status_code == 422
    exported = client.get("/api/v1/admin/reports/attendance.csv?status=present")
    assert exported.status_code == 200, exported.text
    assert "ID-F2" not in exported.text
    assert "ID-F" in exported.text
    assert "'=2+2" in exported.text
    assert "' =1+1" in exported.text


def test_saved_default_attendance_threshold_is_used_for_new_courses(client, make_user):
    make_user("admin", "admin@example.com")
    login(client, "admin@example.com")
    department = client.post("/api/v1/admin/departments", json={"name": "Threshold Department", "code": "TH"})
    assert department.status_code == 201, department.text
    saved = client.put("/api/v1/admin/settings", json={"low_attendance_threshold": 82.5})
    assert saved.status_code == 200, saved.text
    created = client.post("/api/v1/admin/courses", json={
        "department_id": department.json()["id"], "course_code": "TH101", "name": "Threshold Course",
    })
    assert created.status_code == 201, created.text
    assert created.json()["attendance_threshold"] == 82.5
