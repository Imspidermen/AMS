import os
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
TEST_DB = ROOT / "data" / "ssams-tests.sqlite3"
TEST_DB.parent.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SESSION_SECRET"] = "test-only-session-secret-material-" + "x" * 32
os.environ["BIOMETRIC_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
os.environ["APP_ENV"] = "test"
os.environ["COOKIE_SECURE"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import entities  # noqa: F401
from app.core.security import hash_password
from app.models.entities import User


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def make_user():
    def create(role: str, email: str, full_name: str | None = None, password: str = "TestPass12345") -> User:
        with SessionLocal() as db:
            user = User(email=email.lower(), full_name=full_name or email.split("@")[0], role=role,
                        password_hash=hash_password(password), active=True)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
    return create


def login(client: TestClient, email: str, password: str = "TestPass12345"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    client.headers.update({"X-CSRF-Token": response.json()["csrf_token"]})
    return response.json()["user"]
