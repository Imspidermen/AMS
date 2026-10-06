from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from app.core.security import hash_password, verify_password
from app.db.session import SessionLocal
from app.models.entities import (
    Attendance,
    ClassSession,
    Course,
    Department,
    Enrollment,
    Location,
    Semester,
    Student,
    User,
)
from app.services.face import LocalFaceProvider, FaceModelUnavailable, encrypt_embedding, decrypt_embedding
from app.services.geofencing import haversine_distance_m, validate_location_reading
from app.services.liveness import advance_challenge
from app.services.metrics import course_attendance_summary


def test_argon2_password_hashing():
    encoded = hash_password("correct-horse-7612")
    assert encoded.startswith("$argon2id$")
    assert encoded != "correct-horse-7612"
    assert verify_password("correct-horse-7612", encoded)
    assert not verify_password("wrong-password", encoded)


def test_face_embedding_encryption_round_trip():
    embedding = np.array([0.2, -0.5, 0.8], dtype=np.float32)
    encrypted = encrypt_embedding(embedding)
    assert encrypted != embedding.tobytes()
    assert np.allclose(decrypt_embedding(encrypted), embedding)


def test_face_match_threshold_similarity_is_cosine():
    provider = LocalFaceProvider()
    assert provider.similarity(np.array([1, 0]), np.array([1, 0])) == pytest.approx(1.0)
    assert provider.similarity(np.array([1, 0]), np.array([0, 1])) == pytest.approx(0.0)
    assert provider.similarity(np.array([1, 0]), np.array([-1, 0])) == pytest.approx(-1.0)


def test_face_provider_does_not_fake_inference_when_weights_missing(tmp_path):
    provider = LocalFaceProvider(tmp_path)
    assert provider.status()["ready"] is False
    with pytest.raises(FaceModelUnavailable, match="models are missing"):
        provider.analyze(b"not-an-image")


def test_face_provider_status_flags_an_invalid_biometric_storage_key(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "biometric_encryption_key", "replace-with-a-fernet-key")
    state = LocalFaceProvider(tmp_path).status()
    assert state["biometric_storage_key_configured"] is False


def test_face_provider_status_fails_closed_on_wrong_model_digest(tmp_path):
    from app.services.face import SFACE_FILE, YUNET_FILE

    provider = LocalFaceProvider(tmp_path)
    (tmp_path / YUNET_FILE).write_bytes(b"not-the-pinned-model")
    (tmp_path / SFACE_FILE).write_bytes(b"not-the-pinned-model")
    state = provider.status()
    assert state["ready"] is False
    assert state["models"]["sface"]["installed"] is True
    assert state["models"]["sface"]["checksum_valid"] is False
    with pytest.raises(FaceModelUnavailable, match="SHA-256 validation failed"):
        provider.analyze(b"not-an-image")


def test_haversine_distance_and_coordinate_validation():
    # Approximately 111.2 km per degree of latitude at the equator.
    assert haversine_distance_m(0, 0, 1, 0) == pytest.approx(111_195, rel=0.002)
    assert haversine_distance_m(0, 0, 0, 0) == 0
    with pytest.raises(ValueError):
        haversine_distance_m(91, 0, 0, 0)
    with pytest.raises(ValueError):
        haversine_distance_m(float("nan"), 0, 0, 0)


def test_geofence_accuracy_staleness_and_radius_policies():
    location = Location(department_id="d", name="Lab", latitude=51.5, longitude=-0.12,
                        radius_m=100, max_accuracy_m=25, active=True)
    now = datetime.now(timezone.utc)
    assert validate_location_reading(location, 51.5001, -0.12, 10, now, now).accepted
    outside = validate_location_reading(location, 51.51, -0.12, 10, now, now)
    assert not outside.accepted and outside.reason == "outside_geofence"
    inaccurate = validate_location_reading(location, 51.5, -0.12, 45, now, now)
    assert not inaccurate.accepted and inaccurate.reason == "inaccurate_location"
    stale = validate_location_reading(location, 51.5, -0.12, 10, now - timedelta(minutes=5), now)
    assert not stale.accepted and stale.reason == "stale_location"


class SequenceAnalyzer:
    def __init__(self, values):
        self.values = list(values)

    def measure(self, frame):
        return self.values.pop(0)


def _challenge(now, actions=("blink", "turn_left", "return_neutral")):
    return SimpleNamespace(
        expires_at=now + timedelta(seconds=90), consumed_at=None, completed_at=None,
        actions=list(actions), progress={}, frame_count=0,
    )


def test_liveness_requires_distinct_temporal_blink_turn_and_neutral_frames():
    start = datetime.now(timezone.utc)
    challenge = _challenge(start)
    open_eyes = {"face_count": 1, "ear": 0.30, "yaw": 0.0}
    closed_eyes = {"face_count": 1, "ear": 0.10, "yaw": 0.0}
    values = [open_eyes, closed_eyes, open_eyes,
              {"face_count": 1, "ear": 0.30, "yaw": 0.20},
              {"face_count": 1, "ear": 0.30, "yaw": 0.0},
              {"face_count": 1, "ear": 0.30, "yaw": 0.0},
              {"face_count": 1, "ear": 0.30, "yaw": 0.0},
              {"face_count": 1, "ear": 0.30, "yaw": 0.0},
          ]
    analyzer = SequenceAnalyzer(values)
    result = None
    for index in range(8):
        result = advance_challenge(challenge, analyzer, f"unique-frame-{index}".encode(),
                                  start + timedelta(seconds=index * 0.25))
    assert result["complete"] is True
    assert result["progress"] == 3
    assert challenge.completed_at is not None


def test_liveness_repeated_still_frame_does_not_complete_challenge():
    start = datetime.now(timezone.utc)
    challenge = _challenge(start)
    analyzer = SequenceAnalyzer([{"face_count": 1, "ear": 0.30, "yaw": 0.0}])
    first = advance_challenge(challenge, analyzer, b"same-photo", start)
    second = advance_challenge(challenge, analyzer, b"same-photo", start + timedelta(seconds=1))
    assert first["complete"] is False
    assert second["error"] == "duplicate_frame"
    assert second["progress"] == 0
    assert challenge.completed_at is None


def test_expired_challenge_is_rejected():
    start = datetime.now(timezone.utc)
    challenge = _challenge(start)
    result = advance_challenge(challenge, SequenceAnalyzer([]), b"any-frame", start + timedelta(seconds=91))
    assert result["error"] == "expired"
    assert result["complete"] is False


def test_attendance_percentages_exclude_cancelled_and_excused_sessions_and_include_missing_as_absent():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = User(email="metric@example.com", full_name="Metric Student", role="student",
                    password_hash="hash", active=True)
        department = Department(name="Science", code="SCI")
        db.add_all([user, department])
        db.flush()
        student = Student(user_id=user.id, student_number="STU-METRIC", department_id=department.id)
        course = Course(department_id=department.id, course_code="BIO101", name="Biology",
                        attendance_threshold=75.0)
        db.add_all([student, course])
        db.flush()
        enrollment = Enrollment(student_id=student.id, course_id=course.id, active=True)
        location = Location(department_id=department.id, name="Room", latitude=0, longitude=0)
        db.add_all([enrollment, location])
        db.flush()
        sessions = []
        for idx, cancelled in enumerate([False, False, False, False, True]):
            session = ClassSession(course_id=course.id, location_id=location.id, title=f"Session {idx}",
                                   starts_at=now - timedelta(days=idx + 2), ends_at=now - timedelta(days=idx + 2) + timedelta(hours=1),
                                   grace_minutes=10, cancelled=cancelled, created_by=user.id)
            db.add(session)
            sessions.append(session)
        db.flush()
        db.add_all([
            Attendance(student_id=student.id, session_id=sessions[0].id, status="present", marked_at=now),
            Attendance(student_id=student.id, session_id=sessions[1].id, status="late", marked_at=now),
            Attendance(student_id=student.id, session_id=sessions[2].id, status="excused", marked_at=now),
        ])
        db.commit()
        summary = course_attendance_summary(db, student, course, now)
    assert summary["total_eligible_sessions"] == 3
    assert summary["present"] == 1
    assert summary["late"] == 1
    assert summary["excused"] == 1
    assert summary["absent"] == 1
    assert summary["percentage"] == pytest.approx(66.67)
    assert summary["below_threshold"] is True
