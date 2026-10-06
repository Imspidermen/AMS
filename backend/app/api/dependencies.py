from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import User, UserSession
from app.core.security import secret_hash, utc_now

SESSION_COOKIE = "ssams_session"
CSRF_COOKIE = "ssams_csrf"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        token_digest = secret_hash(raw_token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured") from exc
    record = db.query(UserSession).filter(UserSession.token_hash == token_digest).first()
    now = utc_now()
    if not record or _as_utc(record.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = db.get(User, record.user_id)
    if not user or not user.active or not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")
    record.last_seen_at = now
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return value.astimezone(utc_now().tzinfo)
