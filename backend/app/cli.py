"""Operational commands for secrets, first administrator, migrations, and local models."""
from argparse import ArgumentParser
from datetime import timedelta
import getpass
import hashlib
import os
from pathlib import Path
import secrets
import sys
import urllib.request

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.core.config import REPO_ROOT, settings
from app.core.security import ensure_password_policy, hash_password
from app.db.session import SessionLocal
from app.models.entities import AuditEvent, FaceEnrollment, LivenessChallenge, User, UserSession, VerificationAttempt
from app.services.face import LocalFaceProvider, SFACE_FILE, SFACE_SHA256, YUNET_FILE, YUNET_SHA256

MODEL_SOURCES = {
    YUNET_FILE: ("https://media.githubusercontent.com/media/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet/face_detection_yunet_2023mar.onnx", YUNET_SHA256),
    SFACE_FILE: ("https://media.githubusercontent.com/media/opencv/opencv_zoo/ba91a3b91d00d76e86540d4013f944bd6b514e39/models/face_recognition_sface/face_recognition_sface_2021dec.onnx", SFACE_SHA256),
}


def generate_secrets() -> None:
    print("Add these values to your private .env file. Do not commit or share them.")
    print(f"SESSION_SECRET={secrets.token_urlsafe(48)}")
    print(f"BIOMETRIC_ENCRYPTION_KEY={Fernet.generate_key().decode('ascii')}")


def create_admin() -> None:
    with SessionLocal() as db:
        if db.query(User).filter(User.role == "admin").count():
            raise SystemExit("An administrator already exists; refusing to create another bootstrap account.")
        email = input("Administrator email: ").strip().lower()
        full_name = input("Administrator name: ").strip()
        password = getpass.getpass("Administrator password (12+ characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match")
        try:
            ensure_password_policy(password)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if db.query(User).filter(User.email == email).first():
            raise SystemExit("That email address is already registered")
        user = User(email=email, full_name=full_name, role="admin", password_hash=hash_password(password), active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(AuditEvent(actor_user_id=user.id, action="bootstrap.admin_created", entity_type="user", entity_id=user.id))
        db.commit()
        print(f"Administrator account created: {email}")


def install_models(accept_terms: bool) -> None:
    if not accept_terms:
        raise SystemExit("Review models/MODEL_CARD.md and re-run with --accept-model-terms to install weights.")
    output = settings.models_path
    output.mkdir(parents=True, exist_ok=True)
    print("The SFace model is published in OpenCV Zoo under Apache-2.0. Review the model-card cautions about upstream training-data provenance and obtain institution/legal approval before deployment.")
    for filename, (url, expected) in MODEL_SOURCES.items():
        destination = output / filename
        if destination.exists():
            actual = _sha256(destination)
            if actual == expected:
                print(f"Already installed and verified: {destination.name}")
                continue
            raise SystemExit(f"Refusing to overwrite existing file with an unexpected checksum: {destination}")
        temporary = destination.with_suffix(destination.suffix + ".download")
        request = urllib.request.Request(url, headers={"User-Agent": "SSAMS-model-installer/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as target:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise SystemExit(f"Could not download {filename}: {type(exc).__name__}: {exc}") from exc
        actual = _sha256(temporary)
        if actual != expected:
            temporary.unlink(missing_ok=True)
            raise SystemExit(f"Checksum mismatch for {filename}: expected {expected}, got {actual}")
        os.replace(temporary, destination)
        print(f"Installed and verified {destination} (SHA-256 {actual})")
    print("Pinned local model files verified. No model download is needed at application startup.")


def migrate() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    print("Database migrated to the latest Alembic revision.")


def model_check() -> None:
    provider = LocalFaceProvider()
    state = provider.status()
    print(f"Model files ready: {state['ready']}")
    if not state["ready"]:
        for item in state["models"].values():
            if not item["installed"]:
                print(f"Missing: {item['file']}")
        raise SystemExit(2)
    try:
        provider._load()
        import mediapipe as mp

        mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=2)
        mesh.close()
    except Exception as exc:
        raise SystemExit(f"Local model or MediaPipe initialization failed: {type(exc).__name__}: {exc}") from exc
    print("OpenCV YuNet/SFace and MediaPipe Face Mesh loaded successfully on the local CPU runtime.")


def retention(args) -> None:
    if args.verification_days < 1 or args.challenge_days < 1:
        raise SystemExit("Retention days must be at least 1")
    from app.core.security import utc_now

    now = utc_now()
    verification_cutoff = now - timedelta(days=args.verification_days)
    challenge_cutoff = now - timedelta(days=args.challenge_days)
    with SessionLocal() as db:
        verifications = db.query(VerificationAttempt).filter(VerificationAttempt.created_at < verification_cutoff).count()
        challenges = db.query(LivenessChallenge).filter(LivenessChallenge.created_at < challenge_cutoff).count()
        sessions = db.query(UserSession).filter(UserSession.expires_at < now).count()
        biometric_count = 0
        if args.include_biometrics:
            if not args.apply:
                print("Biometric deletion is only applied with --apply; this is a dry run.")
            else:
                if not args.confirm_biometrics:
                    raise SystemExit("Pass --confirm-biometrics to apply biometric template deletion")
                face_cutoff = now - timedelta(days=args.biometric_days)
                biometric_count = db.query(FaceEnrollment).filter(FaceEnrollment.created_at < face_cutoff).count()
        print(f"Expired sessions: {sessions}; old verification attempts: {verifications}; old liveness challenges: {challenges}; old biometric templates: {biometric_count}")
        if not args.apply:
            print("Dry run only. Add --apply to delete the listed expired verification metadata and sessions.")
            return
        db.query(UserSession).filter(UserSession.expires_at < now).delete(synchronize_session=False)
        db.query(LivenessChallenge).filter(LivenessChallenge.created_at < challenge_cutoff).delete(synchronize_session=False)
        db.query(VerificationAttempt).filter(VerificationAttempt.created_at < verification_cutoff).delete(synchronize_session=False)
        if args.include_biometrics:
            face_cutoff = now - timedelta(days=args.biometric_days)
            db.query(FaceEnrollment).filter(FaceEnrollment.created_at < face_cutoff).delete(synchronize_session=False)
        db.commit()
        print("Retention cleanup applied. Attendance and audit records were not deleted.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = ArgumentParser(prog="python -m app.cli", description="SSAMS local operations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("generate-secrets", help="Print cryptographically random secret values")
    subparsers.add_parser("create-admin", help="Interactively create the first administrator")
    subparsers.add_parser("migrate", help="Apply Alembic migrations")
    install = subparsers.add_parser("install-models", help="Download and checksum approved local models")
    install.add_argument("--accept-model-terms", action="store_true")
    subparsers.add_parser("model-check", help="Verify models and initialize local CPU inference")
    clean = subparsers.add_parser("retention", help="Show or apply retention cleanup (dry-run by default)")
    clean.add_argument("--verification-days", type=int, default=90)
    clean.add_argument("--challenge-days", type=int, default=30)
    clean.add_argument("--apply", action="store_true")
    clean.add_argument("--include-biometrics", action="store_true")
    clean.add_argument("--biometric-days", type=int, default=365)
    clean.add_argument("--confirm-biometrics", action="store_true")
    args = parser.parse_args()
    if args.command == "generate-secrets":
        generate_secrets()
    elif args.command == "create-admin":
        create_admin()
    elif args.command == "migrate":
        migrate()
    elif args.command == "install-models":
        install_models(args.accept_model_terms)
    elif args.command == "model-check":
        model_check()
    elif args.command == "retention":
        retention(args)


if __name__ == "__main__":
    main()
