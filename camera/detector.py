"""Camera-based drowsiness detection using MediaPipe Face Mesh.

Uses 478 facial landmarks for precise geometric measurements that work
robustly across varying lighting conditions and head angles — a major
upgrade over Haar cascade + pixel-intensity approaches.

Eye Aspect Ratio (EAR):
    EAR = (||P2 - P6|| + ||P3 - P5||) / (2 · ||P1 - P4||)

    Open eyes:   EAR ≈ 0.25 – 0.35
    Closed eyes: EAR → 0
    Threshold:   EAR < 0.22 for ≥ 2 consecutive frames → eyes closed.

Mouth Aspect Ratio (MAR):
    MAR = (Σ vertical lip distances) / (3 × horizontal lip distance)

    Normal:  MAR ≈ 0.1 – 0.2
    Yawning: MAR ≈ 0.5 – 0.8+
    Threshold: MAR > 0.55, sustained ≥ 2.5 s → yawn registered (8 s cooldown).
"""

import time
import cv2
import numpy as np
import mediapipe as mp
from pathlib import Path
from collections import deque
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import drawing_utils as mp_draw
from mediapipe.tasks.python.vision.drawing_utils import DrawingSpec

# ── Model path ─────────────────────────────────────────────────────────
_MODEL_PATH = str(Path(__file__).parent / "face_landmarker.task")

# ── Landmark indices ───────────────────────────────────────────────────
# 6-point EAR (P1 outer corner … P6 lower-outer) per the standard formula
RIGHT_EYE_EAR = [33, 160, 158, 133, 153, 144]
LEFT_EYE_EAR  = [362, 385, 387, 263, 373, 380]

# Inner-lip MAR landmarks (upper↔lower vertical pairs + horizontal corners)
_MOUTH_VERT  = [(82, 87), (13, 14), (312, 317)]
_MOUTH_HORIZ = (78, 308)

# ── Precompute contour vertex set (for drawing small dots) ─────────────
_CONTOUR_INDICES: frozenset = frozenset(
    idx
    for conn in mp_vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS
    for idx in (conn.start, conn.end)
)

# ── Drawing constants ──────────────────────────────────────────────────
_LINE_SPEC  = DrawingSpec(color=(0, 140, 0), thickness=1, circle_radius=0)
_DOT_COLOR  = (0, 180, 0)   # olive-green, matches reference image
_DOT_RADIUS = 1             # minimal but visible


# ── Helper functions ───────────────────────────────────────────────────
def _dist(p1, p2):
    """Euclidean distance between two (x, y) tuples."""
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def _ear(lm, indices, w, h):
    """Eye Aspect Ratio from 6 landmark indices [P1…P6]."""
    p = [(lm[i].x * w, lm[i].y * h) for i in indices]
    v1 = _dist(p[1], p[5])   # ||P2 - P6||
    v2 = _dist(p[2], p[4])   # ||P3 - P5||
    hz = _dist(p[0], p[3])   # ||P1 - P4||
    return (v1 + v2) / (2.0 * hz) if hz > 1e-6 else 0.0


def _mar(lm, w, h):
    """Mouth Aspect Ratio from inner-lip landmarks."""
    def pt(i):
        return (lm[i].x * w, lm[i].y * h)
    vert = sum(_dist(pt(u), pt(d)) for u, d in _MOUTH_VERT)
    hz   = _dist(pt(_MOUTH_HORIZ[0]), pt(_MOUTH_HORIZ[1]))
    return vert / (3.0 * hz) if hz > 1e-6 else 0.0


class CameraDetector(QThread):
    """Captures camera frames, detects drowsiness via MediaPipe FaceLandmarker.

    Emits the same signals as the previous Haar-cascade detector so the
    rest of the application requires zero changes.
    """

    frame_ready          = Signal(QImage)
    detection_update     = Signal(float, float, float, float)  # eyes_closed_s, yawns/min, ear, mar
    calibration_complete = Signal(float)                        # ear_threshold
    status_changed       = Signal(str)                          # "Running" / "Stopped" / "Error"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

        # EAR config
        self._ear_threshold = 0.22
        self._ear_consec    = 2   # frames before confirming closure

        # Eye-closure state
        self._eyes_closed_start    = None
        self._eyes_closed_duration = 0.0
        self._closed_frames        = 0

        # MAR / yawn config
        self._mar_threshold   = 0.55
        self._yawn_duration_s = 4.0   # 4 s of mouth-open = one yawn
        self._yawn_cooldown_s = 8.0

        # Yawn state
        self._yawn_timestamps    = deque(maxlen=500)
        self._mouth_open_start   = None
        self._yawn_registered    = False
        self._last_yawn_time     = 0.0
        self._mouth_open_frames  = 0

    # ── public API ──────────────────────────────────────────────────
    @property
    def running(self):
        return self._running

    def start_capture(self):
        if self._running:
            return
        self._running              = True
        self._eyes_closed_start    = None
        self._eyes_closed_duration = 0.0
        self._closed_frames        = 0
        self._yawn_timestamps.clear()
        self._mouth_open_start  = None
        self._yawn_registered   = False
        self._last_yawn_time    = 0.0
        self._mouth_open_frames = 0
        self.start()

    def stop_capture(self):
        self._running = False
        self.wait(5000)

    # ── camera open with fallback ───────────────────────────────────
    @staticmethod
    def _open_camera():
        """Try multiple backends; return an opened VideoCapture or None."""
        for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY, -1]:
            try:
                cap = (cv2.VideoCapture(0, backend) if backend != -1
                       else cv2.VideoCapture(0))
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    for _ in range(10):
                        if cap.read()[0]:
                            break
                    ret, test = cap.read()
                    if ret and test is not None and test.size > 0:
                        return cap
                cap.release()
            except Exception:
                try:
                    cap.release()
                except Exception:
                    pass
        return None

    # ── main loop ───────────────────────────────────────────────────
    def run(self):
        cap = self._open_camera()
        if cap is None:
            self.status_changed.emit("Error")
            return

        self.status_changed.emit("Running")
        self.calibration_complete.emit(self._ear_threshold)

        # Create FaceLandmarker (VIDEO mode for sequential frames)
        options = mp_vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        frame_ts = 0  # monotonic timestamp in ms for VIDEO mode

        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    self.msleep(30)
                    continue

                small = cv2.resize(frame, (640, 480))
                small = cv2.flip(small, 1)
                h, w  = small.shape[:2]

                # Convert to MediaPipe Image (RGB)
                rgb      = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                frame_ts += 33  # ~30 fps increment
                results  = landmarker.detect_for_video(mp_image, frame_ts)

                now         = time.time()
                eyes_closed = False
                ear_value   = 0.0
                mar_value   = 0.0

                if results.face_landmarks:
                    lm = results.face_landmarks[0]  # list[NormalizedLandmark]

                    # ── Draw facial landmark mesh (minimal) ──────────
                    mp_draw.draw_landmarks(
                        image=small,
                        landmark_list=lm,
                        connections=list(
                            mp_vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS
                        ),
                        landmark_drawing_spec=None,
                        connection_drawing_spec=_LINE_SPEC,
                        is_drawing_landmarks=False,
                    )
                    # Draw small dots at contour vertices only
                    for idx in _CONTOUR_INDICES:
                        cx = int(lm[idx].x * w)
                        cy = int(lm[idx].y * h)
                        cv2.circle(small, (cx, cy), _DOT_RADIUS, _DOT_COLOR, -1)

                    # ── Face bounding box (from landmarks) ───────────
                    xs = [l.x for l in lm]
                    ys = [l.y for l in lm]
                    x1 = max(0,  int(min(xs) * w) - 10)
                    y1 = max(0,  int(min(ys) * h) - 10)
                    x2 = min(w,  int(max(xs) * w) + 10)
                    y2 = min(h,  int(max(ys) * h) + 10)
                    cv2.rectangle(small, (x1, y1), (x2, y2), (0, 255, 255), 1)

                    # ── EAR (Eye Aspect Ratio) ───────────────────────
                    l_ear     = _ear(lm, LEFT_EYE_EAR, w, h)
                    r_ear     = _ear(lm, RIGHT_EYE_EAR, w, h)
                    ear_value = (l_ear + r_ear) / 2.0

                    if ear_value < self._ear_threshold:
                        self._closed_frames += 1
                    else:
                        self._closed_frames = 0

                    eyes_closed = self._closed_frames >= self._ear_consec

                    if eyes_closed:
                        cv2.putText(small, "EYES CLOSED",
                                    (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                    (0, 0, 255), 2)

                    # ── MAR (Mouth Aspect Ratio) / Yawn ──────────────
                    mar_value     = _mar(lm, w, h)
                    is_mouth_open = mar_value > self._mar_threshold

                    if is_mouth_open:
                        self._mouth_open_frames += 1
                    else:
                        self._mouth_open_frames = 0

                    mouth_confirmed = self._mouth_open_frames >= 2
                    cooldown_ok     = (now - self._last_yawn_time) >= self._yawn_cooldown_s

                    if mouth_confirmed:
                        if self._mouth_open_start is None:
                            self._mouth_open_start = now
                            self._yawn_registered  = False

                        dur = now - self._mouth_open_start

                        if dur >= self._yawn_duration_s and not self._yawn_registered and cooldown_ok:
                            self._yawn_timestamps.append(now)
                            self._last_yawn_time  = now
                            self._yawn_registered = True
                            cv2.putText(small, "YAWN DETECTED!",
                                        (x1, y2 + 25),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                        (0, 0, 255), 2)
                        elif dur < self._yawn_duration_s:
                            cv2.putText(small,
                                        f"Mouth open: {dur:.1f}s",
                                        (x1, y2 + 25),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                        (255, 255, 0), 2)
                    else:
                        self._mouth_open_start = None
                        self._yawn_registered  = False

                    # ── On-frame metrics ─────────────────────────────
                    ear_col = (0, 0, 255) if eyes_closed else (0, 255, 0)
                    mar_col = (0, 0, 255) if mar_value > self._mar_threshold else (0, 255, 0)
                    cv2.putText(small, f"EAR: {ear_value:.2f}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, ear_col, 2)
                    cv2.putText(small, f"MAR: {mar_value:.2f}", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, mar_col, 2)

                else:
                    # No face — reset transient state
                    self._closed_frames     = 0
                    self._mouth_open_start  = None
                    self._yawn_registered   = False
                    self._mouth_open_frames = 0

                # ── Eye-closed duration tracking ─────────────────────
                if eyes_closed and results.face_landmarks:
                    if self._eyes_closed_start is None:
                        self._eyes_closed_start = now
                    self._eyes_closed_duration = now - self._eyes_closed_start
                else:
                    self._eyes_closed_start    = None
                    self._eyes_closed_duration = 0.0

                # ── Yawn rate (rolling 10-minute window) ─────────────
                cutoff = now - 600.0
                yawns_in_10min = sum(1 for t in self._yawn_timestamps if t > cutoff)

                self.detection_update.emit(
                    self._eyes_closed_duration,
                    float(yawns_in_10min),
                    ear_value,
                    mar_value,
                )

                # ── Emit preview frame ───────────────────────────────
                display = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                qh, qw, ch = display.shape
                qimg = QImage(
                    display.tobytes(), qw, qh, ch * qw,
                    QImage.Format.Format_RGB888,
                )
                self.frame_ready.emit(qimg.copy())

                self.msleep(33)  # ~30 fps

        finally:
            landmarker.close()
            cap.release()
            self._running              = False
            self._eyes_closed_start    = None
            self._eyes_closed_duration = 0.0
            self.status_changed.emit("Stopped")
