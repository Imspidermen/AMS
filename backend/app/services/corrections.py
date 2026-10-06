from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Attendance, CorrectionRequest
from app.models.entities import User
from app.services.audit import audit
from app.core.security import utc_now


def resolve_correction(db: Session, item: CorrectionRequest, actor: User, approved: bool, reason: str):
    if item.status != "pending":
        raise HTTPException(409, "Correction request has already been resolved")
    item.status = "approved" if approved else "rejected"
    item.decision_reason = reason.strip()
    item.decided_by = actor.id
    item.decided_at = utc_now()
    if approved:
        attendance = db.query(Attendance).filter(Attendance.student_id == item.student_id,
                                                  Attendance.session_id == item.session_id).first()
        old_status = attendance.status if attendance else None
        if attendance:
            attendance.status = item.requested_status
            attendance.correction_reason = f"Approved correction request {item.id}: {item.reason}"
            attendance.updated_by = actor.id
            attendance.updated_at = utc_now()
        else:
            attendance = Attendance(student_id=item.student_id, session_id=item.session_id,
                                    status=item.requested_status, marked_at=utc_now(),
                                    correction_reason=f"Approved correction request {item.id}: {item.reason}",
                                    updated_by=actor.id)
            db.add(attendance)
        audit(db, actor.id, "attendance.correction_approved", "attendance", attendance.id,
              {"request_id": item.id, "from": old_status, "to": item.requested_status,
               "reason": item.reason, "decision_reason": reason.strip()})
    audit(db, actor.id, f"correction.{item.status}", "correction_request", item.id,
          {"decision_reason": reason.strip()})
    db.commit()
    return {"id": item.id, "status": item.status, "decided_at": item.decided_at}
