from functools import lru_cache
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

# India Standard Time. CAMPUS_TIMEZONE is the single source of truth for every business-time
# decision (attendance day, schedules, reports, API timestamps and log lines).
DEFAULT_TIMEZONE = "Asia/Kolkata"


class Settings(BaseSettings):
    app_name: str = "SSAMS"
    app_env: str = "development"
    # Single public port. One FastAPI process serves the built React frontend and the /api routes,
    # so a tunnel only ever has to expose this one port.
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_dist: str = "frontend/dist"
    database_url: str = "sqlite:///../data/ssams.db"
    session_secret: str = ""
    biometric_encryption_key: str = ""
    cookie_secure: bool = False
    session_ttl_hours: int = 12
    # The application timezone. Asia/Kolkata == IST == UTC+05:30.
    campus_timezone: str = DEFAULT_TIMEZONE
    # Empty by default: the frontend and the API share one origin, so no CORS is required. Only list
    # exact origins here for a deliberate cross-origin deployment (never a wildcard with cookies).
    cors_origins: str = ""
    model_dir: str = "models"
    face_match_threshold: float = 0.363
    geofence_max_reading_age_seconds: int = 120
    max_upload_bytes: int = 2_097_152
    low_attendance_threshold: float = 75.0
    liveness_challenge_ttl_seconds: int = 90
    liveness_max_frames: int = 80
    login_window_seconds: int = 900
    login_max_attempts: int = 10

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("campus_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("CAMPUS_TIMEZONE must be a valid IANA timezone name") from exc
        return value

    @field_validator("app_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("APP_PORT must be a valid TCP port between 1 and 65535")
        return value

    @field_validator("face_match_threshold")
    @classmethod
    def validate_face_threshold(cls, value: float) -> float:
        if not 0.0 < value < 1.0:
            raise ValueError("FACE_MATCH_THRESHOLD must be between 0 and 1")
        return value

    @field_validator("low_attendance_threshold")
    @classmethod
    def validate_attendance_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError("LOW_ATTENDANCE_THRESHOLD must be between 0 and 100")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def models_path(self) -> Path:
        path = Path(self.model_dir).expanduser()
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    @property
    def frontend_dist_path(self) -> Path:
        path = Path(self.frontend_dist).expanduser()
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    @property
    def frontend_build_available(self) -> bool:
        return (self.frontend_dist_path / "index.html").is_file()

    @property
    def secure_cookies(self) -> bool:
        return self.cookie_secure or self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def apply_process_timezone() -> None:
    """Point the OS-level timezone of this process at the campus zone.

    This only influences code that reads the host clock through the standard library — log
    timestamps and third-party local-time formatting. No SSAMS business rule depends on it, which is
    why the application behaves identically on a Windows host whose system timezone is UTC or IST.
    ``TZ`` is ignored on Windows (there is no ``time.tzset``), so this is a graceful no-op there.
    """
    os.environ["TZ"] = settings.campus_timezone
    tzset = getattr(time, "tzset", None)
    if callable(tzset):
        tzset()


settings = get_settings()
apply_process_timezone()
