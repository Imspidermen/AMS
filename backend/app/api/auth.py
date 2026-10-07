from datetime import timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CSRF_COOKIE, SESSION_COOKIE, get_current_user
from app.core.config import settings
from app.core.security import (
    ensure_password_policy,
    hash_password,
    new_secret,
    opaque_hash,
    secret_hash,
    verify_password,
)
from app.core.timezone import as_utc, utc_now
from app.db.session import get_db
from app.models.entities import Student, Teacher, User, UserSession
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ActivateInput(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=256)


class UserView(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    active: bool
    student_number: str | None = None
    employee_number: str | None = None


def user_view(db: Session, user: User) -> UserView:
    result = UserView(id=user.id, email=user.email, full_name=user.full_name, role=user.role, active=user.active)
    if user.role == "student":
        profile = db.query(Student).filter(Student.user_id == user.id).first()
        result.student_number = profile.student_number if profile else None
    elif user.role == "teacher":
        profile = db.query(Teacher).filter(Teacher.user_id == user.id).first()
        result.employee_number = profile.employee_number if profile else None
    return result


@router.get("/csrf")
def issue_csrf(request: Request, response: Response, db: Session = Depends(get_db)):
    csrf = request.cookies.get(CSRF_COOKIE)
    session_raw = request.cookies.get(SESSION_COOKIE)
    existing = None
    if csrf and session_raw:
        try:
            record = db.query(UserSession).filter(UserSession.token_hash == secret_hash(session_raw)).first()
            if record and record.csrf_hash == opaque_hash(csrf) and as_utc(record.expires_at) > utc_now():
                existing = csrf
        except RuntimeError:
            existing = None
    token = existing or secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl_hours * 3600,
    )
    return {"csrf_token": token}


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    now = utc_now()
    ip = request.client.host if request.client else "unknown"
    limiter = request.app.state.login_attempts
    state = limiter.get(ip)
    if state and now.timestamp() - state[0] < settings.login_window_seconds and state[1] >= settings.login_max_attempts:
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")
    normalized_email = str(payload.email).strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not user.active or not user.password_hash or not verify_password(payload.password, user.password_hash):
        if not state or now.timestamp() - state[0] >= settings.login_window_seconds:
            limiter[ip] = [now.timestamp(), 1]
        else:
            state[1] += 1
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    limiter.pop(ip, None)
    try:
        session_token = new_secret()
        csrf_token = secrets.token_urlsafe(32)
        db_session = UserSession(
            token_hash=secret_hash(session_token),
            csrf_hash=opaque_hash(csrf_token),
            user_id=user.id,
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
            last_seen_at=now,
        )
        db.add(db_session)
        audit(db, user.id, "auth.login", "user", user.id)
        db.commit()
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Authentication is not configured; set SESSION_SECRET") from exc
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl_hours * 3600,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl_hours * 3600,
    )
    return {"user": user_view(db, user), "csrf_token": csrf_token}


@router.post("/activate")
def activate(payload: ActivateInput, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.activation_hash == opaque_hash(payload.token)).first()
    if not user or not user.activation_expires_at or as_utc(user.activation_expires_at) <= utc_now() or not user.active:
        raise HTTPException(status_code=400, detail="Activation link is invalid or expired")
    try:
        ensure_password_policy(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user.password_hash = hash_password(payload.password)
    user.activation_hash = None
    user.activation_expires_at = None
    user.updated_at = utc_now()
    audit(db, user.id, "account.activated", "user", user.id)
    db.commit()
    return {"message": "Account activated. You can now sign in."}


@router.get("/me", response_model=UserView)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_view(db, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        record = db.query(UserSession).filter(UserSession.token_hash == secret_hash(raw)).first()
        if record:
            db.delete(record)
            audit(db, user.id, "auth.logout", "user", user.id)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", samesite="lax")
    return response


@router.post("/logout-all", status_code=204)
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(UserSession).filter(UserSession.user_id == user.id).delete(synchronize_session=False)
    audit(db, user.id, "auth.logout_all", "user", user.id)
    db.commit()
    return Response(status_code=204)
