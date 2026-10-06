from sqlalchemy.orm import Session

from app.models.entities import AuditEvent


def audit(
    db: Session,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    db.add(event)
    return event
