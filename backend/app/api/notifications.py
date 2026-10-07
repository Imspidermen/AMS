from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.timezone import to_campus, utc_now
from app.db.session import get_db
from app.models.entities import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    total = query.count()
    unread = db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_(None)).count()
    rows = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()
    return {"items": [{"id": row.id, "kind": row.kind, "title": row.title, "message": row.message,
                       "link": row.link, "read": row.read_at is not None,
                       "created_at": to_campus(row.created_at), "read_at": to_campus(row.read_at)}
                      for row in rows], "total": total, "unread": unread, "limit": limit, "offset": offset}


@router.patch("/{notification_id}/read")
def mark_read(notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(Notification).filter(Notification.id == notification_id,
                                         Notification.user_id == user.id).first()
    if not item:
        raise HTTPException(404, "Notification not found")
    if not item.read_at:
        item.read_at = utc_now()
        db.commit()
    return {"id": item.id, "read": True, "read_at": to_campus(item.read_at)}


@router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.query(Notification).filter(Notification.user_id == user.id,
                                           Notification.read_at.is_(None)).update(
        {Notification.read_at: utc_now()}, synchronize_session=False
    )
    db.commit()
    return {"updated": count}
