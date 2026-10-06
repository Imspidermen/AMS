from datetime import timezone
import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import FaceEnrollment, Student, User
from app.services.audit import audit
from app.services.face import (
    FaceInputError,
    FaceModelUnavailable,
    MODEL_ID,
    LocalFaceProvider,
    encrypt_embedding,
)

router = APIRouter(prefix="/face", tags=["face enrollment"])
student_only = require_roles("student")
face_provider = LocalFaceProvider()
CONSENT_VERSION = "biometric-notice-v1"


@router.get("/status")
def face_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    status = face_provider.status()
    if user.role == "student":
        student = db.query(Student).filter(Student.user_id == user.id).first()
        profile = db.query(FaceEnrollment).filter(FaceEnrollment.student_id == student.id).first() if student else None
        status["enrolled"] = profile is not None
        status["enrolled_at"] = profile.created_at if profile else None
    else:
        status["enrolled"] = None
    return status


@router.post("/enroll", status_code=201)
def enroll_face(
    frames: list[UploadFile] = File(...),
    consent: bool = Form(...),
    user: User = Depends(student_only),
    db: Session = Depends(get_db),
):
    if not consent:
        raise HTTPException(422, "Biometric collection consent is required before enrollment")
    if len(frames) != 3:
        raise HTTPException(422, "Submit exactly three separate, live camera frames for enrollment")
    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student or student.enrollment_status != "active":
        raise HTTPException(403, "Student enrollment is not active")
    existing = db.query(FaceEnrollment).filter(FaceEnrollment.student_id == student.id).first()
    if existing:
        raise HTTPException(409, "Face is already enrolled. Ask an administrator to authorize a reset.")
    images = [_read_upload(upload) for upload in frames]
    if len({hashlib.sha256(image).hexdigest() for image in images}) != 3:
        raise HTTPException(422, "Capture three distinct camera frames rather than reusing a still image")
    try:
        evidence = [face_provider.analyze(image) for image in images]
    except FaceModelUnavailable as exc:
        raise HTTPException(503, detail={"code": "face_model_unavailable", "message": str(exc)}) from exc
    except FaceInputError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": str(exc)}) from exc
    similarities = [face_provider.similarity(evidence[0].embedding, item.embedding) for item in evidence[1:]]
    if min(similarities) < settings.face_match_threshold:
        raise HTTPException(422, detail={"code": "inconsistent_samples",
            "message": "The enrollment frames are not consistent. Keep one face in view and capture again."})
    import numpy as np

    embedding = np.mean([item.embedding for item in evidence], axis=0)
    embedding /= np.linalg.norm(embedding)
    try:
        encrypted = encrypt_embedding(embedding)
    except RuntimeError as exc:
        raise HTTPException(503, detail={"code": "biometric_storage_unavailable", "message": str(exc)}) from exc
    record = FaceEnrollment(
        student_id=student.id,
        encrypted_embedding=encrypted,
        model_id=MODEL_ID,
        consent_at=__import__("datetime").datetime.now(timezone.utc),
        consent_version=CONSENT_VERSION,
        enrolled_by=user.id,
    )
    db.add(record)
    db.flush()
    audit(db, user.id, "face_template.enrolled", "face_enrollment", record.id,
          {"student_id": student.id, "model_id": MODEL_ID, "consent_version": CONSENT_VERSION, "sample_count": len(images)})
    db.commit()
    return {"enrolled": True, "model_id": MODEL_ID, "enrolled_at": record.created_at,
            "notice_version": CONSENT_VERSION, "raw_frames_stored": False}


@router.delete("/enrollment", status_code=204)
def delete_own_face_enrollment(user: User = Depends(student_only), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.user_id == user.id).first()
    if not student:
        raise HTTPException(404, "Student profile not found")
    record = db.query(FaceEnrollment).filter(FaceEnrollment.student_id == student.id).first()
    if record:
        record_id = record.id
        db.delete(record)
        audit(db, user.id, "face_template.deleted_by_owner", "face_enrollment", record_id,
              {"student_id": student.id})
        db.commit()
    return None


def _read_upload(upload: UploadFile) -> bytes:
    contents = upload.file.read(settings.max_upload_bytes + 1)
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(413, "Camera frame exceeds the maximum upload size")
    if not contents:
        raise HTTPException(422, "Camera frame is empty")
    return contents
