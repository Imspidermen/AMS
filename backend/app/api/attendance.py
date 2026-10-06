from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.core.config import settings
from app.core.security import opaque_hash, secret_hash, utc_now
from app.db.session import get_db
from app.models.entities import (
    Attendance,
    ClassSession,
    Course,
    Enrollment,
    FaceEnrollment,
    Location,
    LivenessChallenge,
    Notification,
    Student,
    User,
    VerificationAttempt,
)
from app.services.audit import audit
from app.services.face import (
    FaceInputError,
    FaceModelUnavailable,
    LocalFaceProvider,
    decrypt_embedding,
    encrypt_embedding,
)
from app.services.geofencing import validate_location_reading
from app.services.liveness import LivenessUnavailable, MediaPipeLiveness, advance_challenge, create_actions
from app.services.metrics import student_summaries
from app.services.notifications import generate_low_attendance_alerts

router = APIRouter(prefix="/attendance", tags=["attendance"])
student_only = require_roles("student")
face_provider = LocalFaceProvider()
liveness_analyzer = MediaPipeLiveness()


class AttendanceAttemptInput(BaseModel):
    session_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(gt=0, le=100_000)
    measured_at: datetime

    @field_validator("measured_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Location measurement timestamp must include a timezone")
        return value.astimezone(timezone.utc)


@router.get("/sessions")
def eligible_sessions(user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = _student_for_user(db, user)
    if not student or student.enrollment_status != "active":
        return []
    now = utc_now()
    records = (
        db.query(ClassSession, Course, Location)
        .join(Course, Course.id == ClassSession.course_id)
        .join(Location, Location.id == ClassSession.location_id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .filter(Enrollment.student_id == student.id, Enrollment.active.is_(True),
                ClassSession.cancelled.is_(False), Course.active.is_(True), Location.active.is_(True))
        .all()
    )
    seen = set()
    result = []
    for session, course, location in records:
        if session.id in seen or not _enrollment_matches(db, student.id, session):
            continue
        seen.add(session.id)
        start, end = _as_utc(session.starts_at), _as_utc(session.ends_at)
        if start <= now <= end + timedelta(minutes=session.grace_minutes):
            if not db.query(Attendance).filter(Attendance.student_id == student.id,
                                               Attendance.session_id == session.id).first():
                result.append({"id": session.id, "course_id": course.id, "course_code": course.course_code,
                               "course_name": course.name, "title": session.title, "starts_at": start,
                               "ends_at": end, "grace_minutes": session.grace_minutes,
                               "location_name": location.name})
    result.sort(key=lambda row: row["starts_at"])
    return result


@router.post("/attempts", status_code=201)
def start_attempt(payload: AttendanceAttemptInput, user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = _student_for_user(db, user)
    if not student or student.enrollment_status != "active":
        raise HTTPException(403, "Student enrollment is not active")
    session = db.get(ClassSession, payload.session_id)
    if not session or session.cancelled:
        raise HTTPException(404, "Eligible class session not found")
    if not _enrollment_matches(db, student.id, session):
        raise HTTPException(403, "You are not enrolled in this class section")
    existing = db.query(Attendance).filter(Attendance.student_id == student.id,
                                           Attendance.session_id == session.id).first()
    if existing:
        raise HTTPException(409, detail={"code": "already_marked", "message": "Attendance is already recorded for this session."})
    now = utc_now()
    _ensure_session_open(session, now)
    cutoff = now - timedelta(minutes=15)
    recent_attempts = db.query(VerificationAttempt).filter(
        VerificationAttempt.user_id == user.id,
        VerificationAttempt.created_at >= cutoff,
    ).count()
    if recent_attempts >= 5:
        raise HTTPException(429, detail={"code": "verification_rate_limited",
            "message": "Too many recent attempts. Wait 15 minutes or contact your instructor for help."})
    last_failed = db.query(VerificationAttempt).filter(
        VerificationAttempt.user_id == user.id,
        VerificationAttempt.status == "rejected",
        VerificationAttempt.reason.in_(["face_mismatch", "liveness_expired", "liveness_frame_limit"]),
    ).order_by(VerificationAttempt.created_at.desc()).first()
    if last_failed and (_as_utc(now) - _as_utc(last_failed.created_at)).total_seconds() < 30:
        raise HTTPException(429, detail={"code": "verification_cooldown",
            "message": "Please wait 30 seconds before starting another verification attempt."})
    location = db.get(Location, session.location_id)
    if not location:
        raise HTTPException(409, "The classroom location is not configured")
    geo = validate_location_reading(
        location, payload.latitude, payload.longitude, payload.accuracy_m, payload.measured_at,
        now=now, max_age_seconds=settings.geofence_max_reading_age_seconds,
    )
    attempt = VerificationAttempt(
        user_id=user.id,
        session_id=session.id,
        location_id=location.id,
        status="started" if geo.accepted else "rejected",
        reason=geo.reason,
        distance_m=round(geo.distance_m, 2),
        reported_accuracy_m=round(payload.accuracy_m, 2),
        measurement_at=payload.measured_at,
    )
    db.add(attempt)
    db.flush()
    if not geo.accepted:
        audit(db, user.id, "attendance.location_rejected", "verification_attempt", attempt.id,
              {"reason": geo.reason, "distance_m": round(geo.distance_m, 2), "accuracy_m": round(payload.accuracy_m, 2)})
        db.commit()
        raise _location_rejection(geo.reason)
    if not settings.session_secret or len(settings.session_secret) < 32:
        db.rollback()
        raise HTTPException(503, "SESSION_SECRET is not configured. Follow the secret setup instructions.")
    try:
        raw_token = secrets.token_urlsafe(32)
        challenge = LivenessChallenge(
            token_hash=secret_hash(raw_token), user_id=user.id, session_id=session.id,
            verification_attempt_id=attempt.id, actions=create_actions(), progress={}, frame_count=0,
            expires_at=now + timedelta(seconds=settings.liveness_challenge_ttl_seconds),
        )
        db.add(challenge)
        db.flush()
        audit(db, user.id, "attendance.attempt_started", "verification_attempt", attempt.id,
              {"session_id": session.id, "location_id": location.id})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"attempt_id": attempt.id, "challenge_id": challenge.id, "challenge_token": raw_token,
            "actions": challenge.actions, "expires_at": challenge.expires_at,
            "maximum_frames": settings.liveness_max_frames}


@router.post("/challenges/{challenge_id}/frame")
def liveness_frame(
    challenge_id: str,
    frame: UploadFile = File(...),
    x_liveness_token: str = Header(..., alias="X-Liveness-Token"),
    user: User = Depends(student_only),
    db: Session = Depends(get_db),
):
    challenge = _owned_challenge(db, challenge_id, user, x_liveness_token)
    if challenge.completed_at:
        return {"complete": True, "progress": len(challenge.actions), "total": len(challenge.actions)}
    frame_bytes = _read_upload(frame)
    try:
        result = advance_challenge(challenge, liveness_analyzer, frame_bytes, utc_now(), settings.liveness_max_frames)
    except LivenessUnavailable as exc:
        raise HTTPException(503, detail={"code": "liveness_unavailable", "message": str(exc)}) from exc
    except FaceInputError as exc:
        result = {"complete": False, "progress": int((challenge.progress or {}).get("action_index", 0)),
                  "total": len(challenge.actions), "error": exc.code}
    attempt = db.get(VerificationAttempt, challenge.verification_attempt_id)
    if result.get("error") in {"expired", "frame_limit", "consumed"}:
        challenge.consumed_at = utc_now()
        if attempt:
            attempt.status = "rejected"
            attempt.reason = "liveness_" + result["error"]
        audit(db, user.id, "attendance.liveness_rejected", "verification_attempt", challenge.verification_attempt_id,
              {"reason": result["error"]})
    db.commit()
    result["message"] = _liveness_message(result.get("error"))
    return result


@router.post("/challenges/{challenge_id}/submit")
def submit_attendance(
    challenge_id: str,
    frame: UploadFile = File(...),
    x_liveness_token: str = Header(..., alias="X-Liveness-Token"),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=128),
    user: User = Depends(student_only),
    db: Session = Depends(get_db),
):
    challenge = _owned_challenge(db, challenge_id, user, x_liveness_token)
    attempt = db.get(VerificationAttempt, challenge.verification_attempt_id)
    if not attempt:
        raise HTTPException(409, "Verification attempt is no longer available")
    idem_hash = opaque_hash(idempotency_key)
    if challenge.consumed_at:
        if attempt.idempotency_key_hash == idem_hash and attempt.status == "accepted":
            record = db.query(Attendance).filter(Attendance.student_id == _student_for_user(db, user).id,
                                                 Attendance.session_id == challenge.session_id).first()
            if record:
                return _attendance_result(record, replayed=True)
        raise HTTPException(409, detail={"code": "challenge_consumed", "message": "This challenge has already been used. Start a new attempt."})
    if not challenge.completed_at:
        raise HTTPException(409, detail={"code": "liveness_incomplete", "message": "Complete the live blink and head-movement challenge first."})
    student = _student_for_user(db, user)
    session = db.get(ClassSession, challenge.session_id)
    if not student or not session or session.cancelled or not _enrollment_matches(db, student.id, session):
        raise HTTPException(403, "Student is no longer eligible for this class session")
    existing = db.query(Attendance).filter(Attendance.student_id == student.id,
                                           Attendance.session_id == session.id).first()
    if existing:
        raise HTTPException(409, detail={"code": "already_marked", "message": "Attendance is already recorded for this session."})
    _ensure_session_open(session, utc_now())
    enrollment = db.query(FaceEnrollment).filter(FaceEnrollment.student_id == student.id).first()
    if not enrollment:
        raise HTTPException(409, detail={"code": "face_not_enrolled", "message": "Complete face enrollment before marking attendance."})
    frame_bytes = _read_upload(frame)
    try:
        evidence = face_provider.analyze(frame_bytes)
        enrolled = decrypt_embedding(enrollment.encrypted_embedding)
    except FaceModelUnavailable as exc:
        raise HTTPException(503, detail={"code": "face_model_unavailable", "message": str(exc)}) from exc
    except FaceInputError as exc:
        _reject_attempt(db, attempt, challenge, user, exc.code)
        raise HTTPException(422, detail={"code": exc.code, "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(503, detail={"code": "biometric_storage_unavailable", "message": str(exc)}) from exc
    similarity = face_provider.similarity(evidence.embedding, enrolled)
    if similarity < settings.face_match_threshold:
        _reject_attempt(db, attempt, challenge, user, "face_mismatch")
        raise HTTPException(403, detail={"code": "face_mismatch", "message": "Face verification did not match your enrolled profile. Try again or contact support."})
    now = utc_now()
    _ensure_session_open(session, now)
    try:
        attempt.idempotency_key_hash = idem_hash
        attempt.status = "accepted"
        attempt.reason = None
        challenge.consumed_at = now
        status_value = "late" if now > _as_utc(session.starts_at) + timedelta(minutes=session.grace_minutes) else "present"
        record = Attendance(
            student_id=student.id,
            session_id=session.id,
            status=status_value,
            marked_at=now,
            verification_attempt_id=attempt.id,
        )
        db.add(record)
        db.flush()
        audit(db, user.id, "attendance.marked", "attendance", record.id,
              {"session_id": session.id, "status": status_value, "verification_attempt_id": attempt.id})
        generate_low_attendance_alerts(db, student, user)
        db.commit()
        return _attendance_result(record)
    except IntegrityError:
        db.rollback()
        duplicate = db.query(Attendance).filter(Attendance.student_id == student.id,
                                                Attendance.session_id == session.id).first()
        if duplicate:
            raise HTTPException(409, detail={"code": "already_marked", "message": "Attendance has already been recorded."})
        raise HTTPException(409, detail={"code": "idempotency_conflict", "message": "This request key has already been used."})


@router.get("/history")
def attendance_history(
    course_id: str | None = None,
    state: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(student_only),
    db: Session = Depends(get_db),
):
    student = _student_for_user(db, user)
    if not student:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    query = (
        db.query(Attendance, ClassSession, Course)
        .join(ClassSession, ClassSession.id == Attendance.session_id)
        .join(Course, Course.id == ClassSession.course_id)
        .filter(Attendance.student_id == student.id)
    )
    if course_id:
        query = query.filter(Course.id == course_id)
    if state:
        query = query.filter(Attendance.status == state)
    total = query.count()
    rows = query.order_by(Attendance.marked_at.desc()).offset(offset).limit(limit).all()
    items = [{"id": record.id, "session_id": session.id, "course_id": course.id,
              "course_code": course.course_code, "course_name": course.name, "status": record.status,
              "marked_at": record.marked_at, "title": session.title, "starts_at": session.starts_at,
              "correction_reason": record.correction_reason} for record, session, course in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/summary")
def attendance_summary(user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = _student_for_user(db, user)
    if not student:
        return {"courses": [], "overall_percentage": None, "eligible_sessions": 0, "attended": 0}
    summaries = student_summaries(db, student)
    generate_low_attendance_alerts(db, student, user, summaries)
    db.commit()
    denominators = sum(row["total_eligible_sessions"] for row in summaries)
    attended = sum(row["attended"] for row in summaries)
    return {"courses": summaries,
            "overall_percentage": round(attended * 100.0 / denominators, 2) if denominators else None,
            "eligible_sessions": denominators,
            "attended": attended,
            "threshold": min((row["threshold"] for row in summaries), default=settings.low_attendance_threshold)}


def _student_for_user(db: Session, user: User) -> Student | None:
    return db.query(Student).filter(Student.user_id == user.id).first()


def _enrollment_matches(db: Session, student_id: str, session: ClassSession) -> bool:
    query = db.query(Enrollment).filter(Enrollment.student_id == student_id,
                                        Enrollment.course_id == session.course_id,
                                        Enrollment.active.is_(True))
    if session.section_id:
        query = query.filter(Enrollment.section_id == session.section_id)
    return query.first() is not None


def _ensure_session_open(session: ClassSession, now: datetime):
    start, end = _as_utc(session.starts_at), _as_utc(session.ends_at)
    if now < start:
        raise HTTPException(409, detail={"code": "session_not_started", "message": "Attendance is not open yet."})
    if now > end + timedelta(minutes=session.grace_minutes):
        raise HTTPException(409, detail={"code": "session_closed", "message": "The attendance window for this class has closed."})


def _owned_challenge(db: Session, challenge_id: str, user: User, raw_token: str) -> LivenessChallenge:
    challenge = db.get(LivenessChallenge, challenge_id)
    if not challenge or challenge.user_id != user.id:
        raise HTTPException(404, "Liveness challenge not found")
    try:
        valid = secrets.compare_digest(challenge.token_hash, secret_hash(raw_token))
    except RuntimeError as exc:
        raise HTTPException(503, "Authentication secrets are not configured") from exc
    if not valid:
        raise HTTPException(403, "Liveness challenge token is invalid")
    return challenge


def _read_upload(file: UploadFile) -> bytes:
    contents = file.file.read(settings.max_upload_bytes + 1)
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(413, "Camera frame exceeds the maximum upload size")
    if not contents:
        raise HTTPException(422, "Camera frame is empty")
    return contents


def _location_rejection(reason: str | None) -> HTTPException:
    if reason == "outside_geofence":
        return HTTPException(403, detail={"code": reason,
            "message": "You are too far from the permitted classroom area to mark attendance."})
    if reason in {"inaccurate_location", "invalid_accuracy", "stale_location"}:
        return HTTPException(422, detail={"code": reason,
            "message": "Your location is not accurate enough. Move to an open area and try again."})
    return HTTPException(422, detail={"code": reason or "location_rejected",
        "message": "Location verification failed. Check location permission and try again."})


def _liveness_message(code: str | None) -> str:
    return {
        "no_face": "No face was detected. Move into view and face the camera.",
        "multiple_faces": "Only one person should be visible to the camera.",
        "expired": "The challenge expired. Start a new attendance attempt.",
        "frame_limit": "The challenge reached its frame limit. Start a new attempt.",
        "duplicate_frame": "Move your face; a repeated camera frame was ignored.",
        "frame_too_fast": "Move naturally and follow the challenge prompts.",
    }.get(code or "", "Follow the prompts: blink, turn your head, then return to neutral.")


def _reject_attempt(db: Session, attempt: VerificationAttempt, challenge: LivenessChallenge, user: User, reason: str):
    attempt.status = "rejected"
    attempt.reason = reason
    challenge.consumed_at = utc_now()
    audit(db, user.id, "attendance.verification_rejected", "verification_attempt", attempt.id,
          {"reason": reason, "session_id": attempt.session_id})
    db.commit()


def _attendance_result(record: Attendance, replayed: bool = False) -> dict:
    return {"attendance_id": record.id, "session_id": record.session_id, "status": record.status,
            "marked_at": record.marked_at, "message": "Attendance recorded successfully.", "replayed": replayed}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
