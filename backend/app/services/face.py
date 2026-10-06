"""Local, CPU-only face detection and 1:1 embedding comparison (YuNet + SFace)."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import threading

import cv2
import numpy as np

from app.core.config import settings

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
SFACE_SHA256 = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
MODEL_ID = "opencv-zoo-yunet-2023mar+sface-2021dec"


class FaceModelUnavailable(RuntimeError):
    pass


class FaceInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class FaceEvidence:
    embedding: np.ndarray
    face_count: int
    blur_score: float
    brightness: float
    yaw_estimate: float
    roll_degrees: float


class LocalFaceProvider:
    """Loads licensed model files from disk; it never downloads weights at runtime."""

    def __init__(self, model_dir: Path | None = None):
        self.model_dir = model_dir or settings.models_path
        self._detector = None
        self._recognizer = None
        self._lock = threading.RLock()

    @property
    def model_files(self) -> dict[str, Path]:
        return {"yunet": self.model_dir / YUNET_FILE, "sface": self.model_dir / SFACE_FILE}

    def status(self) -> dict:
        paths = self.model_files
        expected = {"yunet": YUNET_SHA256, "sface": SFACE_SHA256}
        model_status = {}
        for name, path in paths.items():
            installed = path.is_file()
            try:
                valid = installed and _sha256(path) == expected[name]
            except OSError:
                valid = False
            model_status[name] = {"file": path.name, "installed": installed, "checksum_valid": valid}
        return {
            "provider": MODEL_ID,
            "inference": "local_cpu",
            "ready": all(model["checksum_valid"] for model in model_status.values()),
            "models": model_status,
            "biometric_storage_key_configured": _valid_biometric_key(settings.biometric_encryption_key),
        }

    def _load(self) -> None:
        with self._lock:
            if self._detector is not None and self._recognizer is not None:
                return
            missing = [path.name for path in self.model_files.values() if not path.is_file()]
            if missing:
                raise FaceModelUnavailable(
                    "Required local face models are missing: " + ", ".join(missing)
                    + ". Run `python -m app.cli install-models --accept-model-terms` after reviewing models/MODEL_CARD.md."
                )
            for name, path in self.model_files.items():
                expected = YUNET_SHA256 if name == "yunet" else SFACE_SHA256
                digest = _sha256(path)
                if digest != expected:
                    raise FaceModelUnavailable(f"SHA-256 validation failed for {path.name}; reinstall the pinned model.")
            try:
                detector_path = str(self.model_files["yunet"])
                recognizer_path = str(self.model_files["sface"])
                self._detector = cv2.FaceDetectorYN.create(detector_path, "", (320, 320), 0.85, 0.3, 5000)
                self._recognizer = cv2.FaceRecognizerSF.create(recognizer_path, "")
            except Exception as exc:
                self._detector = None
                self._recognizer = None
                raise FaceModelUnavailable(f"OpenCV could not load the face models: {type(exc).__name__}") from exc

    def analyze(self, image_bytes: bytes, minimum_face_pixels: int = 100) -> FaceEvidence:
        self._load()
        image = decode_image(image_bytes)
        height, width = image.shape[:2]
        if min(width, height) < 160 or max(width, height) > 3000:
            raise FaceInputError("invalid_dimensions", "Use a camera image between 160 and 3000 pixels in size.")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(gray.mean())
        if brightness < 30 or brightness > 235:
            raise FaceInputError("poor_lighting", "Lighting is too dark or bright. Face a well-lit area and try again.")
        self._detector.setInputSize((width, height))
        _, faces = self._detector.detect(image)
        face_count = 0 if faces is None else len(faces)
        if face_count == 0:
            raise FaceInputError("no_face", "No face was detected. Center your face in the camera and try again.")
        if face_count != 1:
            raise FaceInputError("multiple_faces", "Only one face may be visible in the camera frame.")
        face = faces[0]
        if min(float(face[2]), float(face[3])) < minimum_face_pixels:
            raise FaceInputError("face_too_small", "Move closer to the camera so your face is clearly visible.")
        right_eye = face[4:6]
        left_eye = face[6:8]
        eye_width = float(np.linalg.norm(right_eye - left_eye))
        if eye_width <= 1e-5:
            raise FaceInputError("pose_unusable", "Face landmarks are unclear. Face the camera directly.")
        nose = face[8:10]
        yaw_estimate = float((nose[0] - (right_eye[0] + left_eye[0]) / 2.0) / eye_width)
        roll_degrees = float(np.degrees(np.arctan2(left_eye[1] - right_eye[1], left_eye[0] - right_eye[0])))
        if abs(yaw_estimate) > 0.38 or abs(roll_degrees) > 20:
            raise FaceInputError("pose_unusable", "Face the camera directly with your head upright.")
        if blur_score < 18:
            raise FaceInputError("blurred", "The image is too blurred. Hold the camera steady and try again.")
        try:
            aligned = self._recognizer.alignCrop(image, face)
            feature = self._recognizer.feature(aligned).reshape(-1).astype(np.float32)
        except Exception as exc:
            raise FaceInputError("face_alignment_failed", "Face alignment failed. Adjust your pose and try again.") from exc
        norm = float(np.linalg.norm(feature))
        if not np.isfinite(norm) or norm <= 1e-8:
            raise FaceInputError("invalid_embedding", "The face could not be verified. Please try again.")
        feature /= norm
        return FaceEvidence(feature, 1, blur_score, brightness, yaw_estimate, roll_degrees)

    def similarity(self, first: np.ndarray, second: np.ndarray) -> float:
        first = np.asarray(first, dtype=np.float32).reshape(-1)
        second = np.asarray(second, dtype=np.float32).reshape(-1)
        if first.shape != second.shape or not first.size:
            return -1.0
        a_norm, b_norm = np.linalg.norm(first), np.linalg.norm(second)
        if a_norm <= 1e-8 or b_norm <= 1e-8:
            return -1.0
        return float(np.dot(first / a_norm, second / b_norm))


def decode_image(image_bytes: bytes) -> np.ndarray:
    if not image_bytes:
        raise FaceInputError("empty_image", "No camera frame was received.")
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise FaceInputError("invalid_image", "The camera frame is not a valid image.")
    return image


def encrypt_embedding(embedding: np.ndarray) -> bytes:
    key = settings.biometric_encryption_key
    if not key:
        raise RuntimeError("BIOMETRIC_ENCRYPTION_KEY is not configured")
    try:
        from cryptography.fernet import Fernet

        fernet = Fernet(key.encode("ascii"))
        body = np.asarray(embedding, dtype=np.float32).tobytes()
        return fernet.encrypt(body)
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("BIOMETRIC_ENCRYPTION_KEY must be a valid Fernet key") from exc


def decrypt_embedding(encrypted: bytes) -> np.ndarray:
    key = settings.biometric_encryption_key
    if not key:
        raise RuntimeError("BIOMETRIC_ENCRYPTION_KEY is not configured")
    from cryptography.fernet import Fernet, InvalidToken

    try:
        body = Fernet(key.encode("ascii")).decrypt(encrypted)
    except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("Biometric template cannot be decrypted; verify the encryption key and backup") from exc
    if len(body) % 4:
        raise RuntimeError("Biometric template has an invalid encrypted payload")
    return np.frombuffer(body, dtype=np.float32).copy()


def _valid_biometric_key(value: str) -> bool:
    if not value:
        return False
    try:
        from cryptography.fernet import Fernet

        Fernet(value.encode("ascii"))
        return True
    except (ValueError, UnicodeError):
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
