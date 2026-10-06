"""Server-side temporal blink/head-pose challenge measurements using MediaPipe Face Mesh."""
import hashlib
import math
import secrets
import threading
from datetime import datetime, timezone

import numpy as np

from app.services.face import FaceInputError, decode_image

BLINK_CLOSED_EAR = 0.19
BLINK_OPEN_EAR = 0.235
HEAD_TURN_YAW = 0.13
NEUTRAL_YAW = 0.075
MIN_CHALLENGE_SECONDS = 1.6
MIN_DISTINCT_FRAMES = 8
MIN_FRAME_INTERVAL_SECONDS = 0.11


class LivenessUnavailable(RuntimeError):
    pass


class MediaPipeLiveness:
    def __init__(self):
        self._mesh = None
        self._lock = threading.RLock()

    def _get_mesh(self):
        with self._lock:
            if self._mesh is None:
                try:
                    import mediapipe as mp

                    self._mesh = mp.solutions.face_mesh.FaceMesh(
                        static_image_mode=True,
                        max_num_faces=2,
                        refine_landmarks=True,
                        min_detection_confidence=0.65,
                    )
                except Exception as exc:
                    raise LivenessUnavailable(
                        "MediaPipe Face Mesh is unavailable. Reinstall the pinned backend vision dependencies."
                    ) from exc
            return self._mesh

    def measure(self, image_bytes: bytes) -> dict:
        try:
            import cv2

            bgr = decode_image(image_bytes)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            with self._lock:
                result = self._get_mesh().process(rgb)
        except FaceInputError:
            raise
        except LivenessUnavailable:
            raise
        except Exception as exc:
            raise LivenessUnavailable(f"Could not analyze the frame ({type(exc).__name__}).") from exc
        faces = result.multi_face_landmarks or []
        if not faces:
            return {"face_count": 0}
        if len(faces) != 1:
            return {"face_count": len(faces)}
        points = faces[0].landmark
        left_ear = _eye_aspect_ratio(points, (33, 160, 158, 133, 153, 144))
        right_ear = _eye_aspect_ratio(points, (362, 385, 387, 263, 373, 380))
        ear = (left_ear + right_ear) / 2.0
        eye_left = points[33].x
        eye_right = points[263].x
        eye_width = abs(eye_right - eye_left)
        if eye_width < 1e-4:
            return {"face_count": 0}
        eye_midpoint = (eye_left + eye_right) / 2.0
        # Signed nose displacement normalized by inter-eye width. Signs are calibrated
        # to the unmirrored image pixels sent by the browser, not the mirrored preview.
        yaw = (points[1].x - eye_midpoint) / eye_width
        if not math.isfinite(ear) or not math.isfinite(yaw):
            return {"face_count": 0}
        return {"face_count": 1, "ear": float(ear), "yaw": float(yaw)}


def create_actions() -> list[str]:
    turn = secrets.choice(["turn_left", "turn_right"])
    sequence = ["blink", turn]
    if secrets.randbelow(2):
        sequence.reverse()
    sequence.append("return_neutral")
    return sequence


def advance_challenge(challenge, analyzer: MediaPipeLiveness, image_bytes: bytes, now: datetime | None = None, max_frames: int = 80) -> dict:
    now = _as_utc(now or datetime.now(timezone.utc))
    expires_at = _as_utc(challenge.expires_at)
    if now >= expires_at:
        return {"complete": False, "progress": 0, "total": len(challenge.actions), "error": "expired"}
    if challenge.consumed_at:
        return {"complete": False, "progress": 0, "total": len(challenge.actions), "error": "consumed"}
    if challenge.completed_at:
        return {"complete": True, "progress": len(challenge.actions), "total": len(challenge.actions)}

    challenge.frame_count += 1
    if challenge.frame_count > max_frames:
        return {"complete": False, "progress": 0, "total": len(challenge.actions), "error": "frame_limit"}
    digest = hashlib.sha256(image_bytes).hexdigest()
    state = dict(challenge.progress or {})
    if digest == state.get("last_digest"):
        challenge.progress = state
        return _progress(challenge, "duplicate_frame")
    observation = analyzer.measure(image_bytes)
    state["last_digest"] = digest
    state["distinct_frames"] = int(state.get("distinct_frames", 0)) + 1
    if not state.get("started_at"):
        state["started_at"] = now.isoformat()
    previous = _parse_time(state.get("last_frame_at"))
    if previous and (now - previous).total_seconds() < MIN_FRAME_INTERVAL_SECONDS:
        state["last_frame_at"] = now.isoformat()
        challenge.progress = state
        return _progress(challenge, "frame_too_fast")
    state["last_frame_at"] = now.isoformat()

    face_count = observation.get("face_count", 0)
    if face_count != 1:
        challenge.progress = state
        reason = "no_face" if face_count == 0 else "multiple_faces"
        return _progress(challenge, reason)

    action_index = int(state.get("action_index", 0))
    if action_index < len(challenge.actions):
        action = challenge.actions[action_index]
        ear, yaw = observation["ear"], observation["yaw"]
        if action == "blink":
            if ear < BLINK_CLOSED_EAR:
                state["blink_closed"] = True
            elif state.get("blink_closed") and ear > BLINK_OPEN_EAR:
                state["action_index"] = action_index + 1
                state["blink_closed"] = False
        elif action == "turn_left" and yaw >= HEAD_TURN_YAW:
            state["action_index"] = action_index + 1
            state["head_moved"] = True
        elif action == "turn_right" and yaw <= -HEAD_TURN_YAW:
            state["action_index"] = action_index + 1
            state["head_moved"] = True
        elif action == "return_neutral":
            if state.get("head_moved") and abs(yaw) <= NEUTRAL_YAW:
                state["neutral_frames"] = int(state.get("neutral_frames", 0)) + 1
                if state["neutral_frames"] >= 2:
                    state["action_index"] = action_index + 1
            else:
                state["neutral_frames"] = 0

    challenge.progress = state
    elapsed = (now - _parse_time(state["started_at"])).total_seconds()
    complete = (
        int(state.get("action_index", 0)) >= len(challenge.actions)
        and int(state.get("distinct_frames", 0)) >= MIN_DISTINCT_FRAMES
        and elapsed >= MIN_CHALLENGE_SECONDS
    )
    if complete:
        challenge.completed_at = now
    result = _progress(challenge)
    result["complete"] = complete
    result["elapsed_seconds"] = round(max(0, elapsed), 2)
    return result


def _progress(challenge, error: str | None = None) -> dict:
    state = challenge.progress or {}
    result = {
        "complete": False,
        "progress": int(state.get("action_index", 0)),
        "total": len(challenge.actions),
        "distinct_frames": int(state.get("distinct_frames", 0)),
    }
    if error:
        result["error"] = error
    return result


def _eye_aspect_ratio(points, indices) -> float:
    coords = np.array([[points[i].x, points[i].y] for i in indices], dtype=np.float64)
    horizontal = float(np.linalg.norm(coords[0] - coords[3]))
    vertical = float(np.linalg.norm(coords[1] - coords[5]) + np.linalg.norm(coords[2] - coords[4]))
    return vertical / (2.0 * horizontal) if horizontal > 1e-8 else 0.0


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)
