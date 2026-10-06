from contextlib import asynccontextmanager
import logging
import secrets
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from starlette import status

from app.api import admin, attendance, auth, face, notifications, reports, student, teacher
from app.api.dependencies import CSRF_COOKIE, SESSION_COOKIE
from app.core.config import settings
from app.core.security import opaque_hash, secret_hash, utc_now
from app.db.session import SessionLocal, engine
from app.models.entities import User, UserSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ssams")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    engine.dispose()


app = FastAPI(
    title="SSAMS — Smart Student Attendance Management System",
    description=("Locally operated attendance management API. Biometric and geolocation checks are "
                 "sensitive and are not guarantees against spoofing."),
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan,
)
app.state.login_attempts = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Liveness-Token", "Idempotency-Key"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    candidate_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        candidate_request_id
        if 0 < len(candidate_request_id) <= 80
        and candidate_request_id.isascii()
        and all(character.isalnum() or character in "-_." for character in candidate_request_id)
        else str(uuid.uuid4())
    )
    request.state.request_id = request_id
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        path = request.url.path
        public_mutations = {"/api/v1/auth/login", "/api/v1/auth/activate"}
        if path not in public_mutations:
            raw_session = request.cookies.get(SESSION_COOKIE)
            if raw_session:
                csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
                csrf_header = request.headers.get("X-CSRF-Token", "")
                if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
                    return JSONResponse(status_code=403, content={"detail": "CSRF validation failed", "request_id": request_id})
                try:
                    digest = secret_hash(raw_session)
                except RuntimeError:
                    return JSONResponse(status_code=503, content={"detail": "Authentication is not configured", "request_id": request_id})
                with SessionLocal() as db:
                    session = db.query(UserSession).filter(UserSession.token_hash == digest).first()
                    if (not session or _as_utc(session.expires_at) <= utc_now()
                            or not secrets.compare_digest(session.csrf_hash, opaque_hash(csrf_header))):
                        return JSONResponse(status_code=403, content={"detail": "Session or CSRF token is invalid", "request_id": request_id})
    content_length = request.headers.get("content-length")
    max_request = settings.max_upload_bytes * 4 + 256_000
    if content_length and content_length.isdigit() and int(content_length) > max_request:
        return JSONResponse(status_code=413, content={"detail": "Request payload is too large", "request_id": request_id})
    try:
        response = await call_next(request)
    except Exception as exc:  # final containment; details are never sent to the client
        logger.error("request failed request_id=%s method=%s path=%s error=%s",
                     request_id, request.method, request.url.path, type(exc).__name__)
        response = JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), geolocation=(self), microphone=()"
    response.headers["Cache-Control"] = "no-store"
    if settings.secure_cookies:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail,
        "request_id": getattr(request.state, "request_id", "")}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [{"loc": error.get("loc", []), "msg": error.get("msg", "Invalid input"), "type": error.get("type", "value_error")}
              for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Request validation failed", "errors": errors,
        "request_id": getattr(request.state, "request_id", "")})


@app.get("/", include_in_schema=False)
def root():
    return {"name": settings.app_name, "api": "/api/v1", "docs": "/api/v1/docs"}


@app.get("/api/v1/health/live", tags=["health"])
def liveness():
    return {"status": "alive", "service": "ssams-api"}


@app.get("/api/v1/health/ready", tags=["health"])
def readiness():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db.execute(select(User.id).limit(1)).all()
    except Exception as exc:
        logger.warning("readiness database check failed error=%s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail={"status": "not_ready", "database": "unavailable_or_unmigrated"}) from exc
    model_status = attendance.face_provider.status()
    return {"status": "ready", "database": "connected", "campus_timezone": settings.campus_timezone, "vision_models": model_status,
            "vision_degraded": not model_status["ready"] or not model_status["biometric_storage_key_configured"],
            "offline_inference": "local CPU; models must be installed explicitly"}


versioned = [
    auth.router,
    admin.router,
    teacher.router,
    student.router,
    attendance.router,
    face.router,
    notifications.router,
    reports.router,
    reports.admin_router,
]
for router in versioned:
    app.include_router(router, prefix="/api/v1")


def _as_utc(value):
    from datetime import timezone

    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
