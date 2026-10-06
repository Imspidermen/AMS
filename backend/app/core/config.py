from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "SSAMS"
    app_env: str = "development"
    database_url: str = "sqlite:///../data/ssams.db"
    session_secret: str = ""
    biometric_encryption_key: str = ""
    cookie_secure: bool = False
    session_ttl_hours: int = 12
    campus_timezone: str = "UTC"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
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
    def secure_cookies(self) -> bool:
        return self.cookie_secure or self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
