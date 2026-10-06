from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.db.base import Base


class UTCDateTime(TypeDecorator):
    """Store UTC datetimes and restore an explicit UTC offset on every dialect."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), index=True)
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    activation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activation_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class AcademicYear(Base):
    __tablename__ = "academic_years"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    starts_on: Mapped[str] = mapped_column(String(10))
    ends_on: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Semester(Base):
    __tablename__ = "semesters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    academic_year_id: Mapped[str] = mapped_column(ForeignKey("academic_years.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    starts_on: Mapped[str] = mapped_column(String(10))
    ends_on: Mapped[str] = mapped_column(String(10))
    __table_args__ = (UniqueConstraint("academic_year_id", "name", name="uq_semester_year_name"),)


class Student(Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True, index=True)
    student_number: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    program: Mapped[str] = mapped_column(String(160), default="")
    semester_id: Mapped[str | None] = mapped_column(ForeignKey("semesters.id", ondelete="SET NULL"), nullable=True)
    enrollment_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True, index=True)
    employee_number: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    semester_id: Mapped[str | None] = mapped_column(ForeignKey("semesters.id", ondelete="SET NULL"), nullable=True)
    course_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    attendance_threshold: Mapped[float] = mapped_column(Float, default=75.0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Section(Base):
    __tablename__ = "sections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_section_course_name"),)


class Enrollment(Base):
    __tablename__ = "enrollments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="RESTRICT"), index=True)
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),)


class TeacherAssignment(Base):
    __tablename__ = "teacher_assignments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"), nullable=True)
    __table_args__ = (UniqueConstraint("teacher_id", "course_id", "section_id", name="uq_teacher_course_section"),)


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float, default=100.0)
    max_accuracy_m: Mapped[float] = mapped_column(Float, default=100.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class ClassSession(Base):
    __tablename__ = "class_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="RESTRICT"), index=True)
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"), nullable=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(180), default="Class session")
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    grace_minutes: Mapped[int] = mapped_column(Integer, default=10)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    __table_args__ = (Index("ix_session_course_start", "course_id", "starts_at"),)


class FaceEnrollment(Base):
    __tablename__ = "face_enrollments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), unique=True, index=True)
    encrypted_embedding: Mapped[bytes] = mapped_column(LargeBinary)
    model_id: Mapped[str] = mapped_column(String(100))
    consent_at: Mapped[datetime] = mapped_column(UTCDateTime())
    consent_version: Mapped[str] = mapped_column(String(40))
    enrolled_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


class VerificationAttempt(Base):
    __tablename__ = "verification_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("class_sessions.id", ondelete="RESTRICT"), index=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="started", index=True)
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    reported_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    __table_args__ = (Index("ix_verification_attempts_idempotency_key_hash", "idempotency_key_hash", unique=True),)


class LivenessChallenge(Base):
    __tablename__ = "liveness_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("class_sessions.id", ondelete="RESTRICT"), index=True)
    verification_attempt_id: Mapped[str] = mapped_column(ForeignKey("verification_attempts.id", ondelete="CASCADE"), unique=True)
    actions: Mapped[list] = mapped_column(JSON)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Attendance(Base):
    __tablename__ = "attendance"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("class_sessions.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    marked_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    verification_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("verification_attempts.id", ondelete="SET NULL"), nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("student_id", "session_id", name="uq_attendance_student_session"),
        Index("ix_attendance_session_status", "session_id", "status"),
    )


class CorrectionRequest(Base):
    __tablename__ = "correction_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("class_sessions.id", ondelete="RESTRICT"), index=True)
    requested_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    submitted_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(String(240), default="")
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
