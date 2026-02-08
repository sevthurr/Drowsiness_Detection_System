"""Camera-based drowsiness detection using OpenCV (Haar Cascades fallback)."""

import time
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class CameraDetector(QThread):
    """Captures camera frames, detects face/eyes, emits drowsiness data."""

    frame_ready = Signal(QImage)
    detection_update = Signal(float, float, float, float)  # eyes_closed_s, yawns/min, ear, mar
    calibration_complete = Signal(float)  # new ear_threshold (stub for compatibility)
    status_changed = Signal(str)  # "Running" / "Stopped" / "Error"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

        # Detection thresholds (simplified for Haar Cascade approach)
        self._eye_aspect_threshold = 0.2

        # Eye closure tracking
        self._eyes_closed_start = None
        self._eyes_detected = True

        # Yawn tracking (simplified)
        self._yawn_timestamps = []
        self._mouth_open_frames = 0

    # ── public API ──────────────────────────────────────────────────
    @property
    def running(self):
        return self._running

    def start_capture(self):
        if self._running:
            return
        self._running = True
        self._eyes_closed_start = None
        self._yawn_timestamps.clear()
        self._mouth_was_open = False
        self.start()

    def stop_capture(self):
        self._running = False
        self.wait(5000)

    # ── camera open with fallback ───────────────────────────────────
    @staticmethod
    def _open_camera():
        """Try multiple backends; return an opened VideoCapture or None."""
        # Try index 0 with different backends
        for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY, -1]:
            try:
                cap = cv2.VideoCapture(0, backend) if backend != -1 else cv2.VideoCapture(0)
                if cap.isOpened():
                    # Set resolution for better compatibility
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    # Warm-up reads
                    for _ in range(10):
                        ret, _ = cap.read()
                        if ret:
                            break
                    # Final test
                    ret, test = cap.read()
                    if ret and test is not None and test.size > 0:
                        return cap
                cap.release()
            except Exception:
                try:
                    cap.release()
                except:
                    pass
        return None

    # ── main loop ───────────────────────────────────────────────────
    def run(self):
        cap = self._open_camera()
        if cap is None:
            self.status_changed.emit("Error")
            return

        self.status_changed.emit("Running")

        # Load OpenCV Haar Cascade classifiers
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )
        
        # Auto-calibration (emit after 2 seconds as compatibility stub)
        calibrated = False
        cal_start = time.time()

        frame_n = 0
        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    self.msleep(30)
                    continue

                frame_n += 1
                small = cv2.resize(frame, (640, 480))
                small = cv2.flip(small, 1)  # Mirror flip

                # Convert to grayscale for detection
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                
                # Detect faces
                faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                
                eyes_closed = True  # Assume closed if no eyes detected
                for (x, y, w, h) in faces:
                    roi_gray = gray[y:y+h, x:x+w]
                    roi_color = small[y:y+h, x:x+w]
                    
                    # Detect eyes in face region
                    eyes = eye_cascade.detectMultiScale(roi_gray, 1.1, 3, minSize=(20, 20))
                    
                    if len(eyes) >= 2:
                        eyes_closed = False
                    
                    # Draw rectangles
                    cv2.rectangle(small, (x, y), (x+w, y+h), (0, 255, 255), 2)
                    for (ex, ey, ew, eh) in eyes:
                        cv2.rectangle(roi_color, (ex, ey), (ex+ew, ey+eh), (0, 255, 0), 2)
                    
                    break  # Only process first face

                # Auto-calibration stub
                if not calibrated and time.time() - cal_start >= 2.0:
                    calibrated = True
                    self.calibration_complete.emit(0.22)

                # Track eyes closed duration
                if eyes_closed and len(faces) > 0:
                    if self._eyes_closed_start is None:
                        self._eyes_closed_start = time.time()
                    eyes_s = time.time() - self._eyes_closed_start
                else:
                    self._eyes_closed_start = None
                    eyes_s = 0.0

                # Emit detection data (yawns=0 for simplified version, EAR/MAR as placeholders)
                self.detection_update.emit(eyes_s, 0.0, 0.25, 0.3)

                # Emit preview frame
                display = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                qh, qw, ch = display.shape
                bpl = ch * qw
                qimg = QImage(
                    display.tobytes(), qw, qh, bpl, QImage.Format.Format_RGB888
                )
                self.frame_ready.emit(qimg.copy())

                self.msleep(33)
        finally:
            cap.release()
            self._running = False
            self._eyes_closed_start = None
            self.status_changed.emit("Stopped")
