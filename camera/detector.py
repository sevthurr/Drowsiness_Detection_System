"""Camera-based drowsiness detection using OpenCV."""

import time
import cv2
import numpy as np
from collections import deque
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class CameraDetector(QThread):
    """Captures camera frames, detects face/eyes/yawns using OpenCV, emits drowsiness data."""

    frame_ready = Signal(QImage)
    detection_update = Signal(float, float, float, float)  # eyes_closed_s, yawns/min, ear, mar
    calibration_complete = Signal(float)  # ear_threshold
    status_changed = Signal(str)  # "Running" / "Stopped" / "Error"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

        # Detection thresholds
        self._ear_threshold = 0.20  # Lower = more sensitive to eye closure
        self._calibrated = False

        # Eye closure tracking
        self._eyes_closed_start = None
        self._eyes_closed_duration = 0.0
        self._consecutive_eye_closed_frames = 0

        # Yawn tracking
        self._yawn_timestamps = deque(maxlen=100)
        self._yawn_cooldown = 0.0
        self._mouth_open_frames = 0
        
        # Calibration
        self._calibration_samples = deque(maxlen=30)

    # ── public API ──────────────────────────────────────────────────
    @property
    def running(self):
        return self._running

    def start_capture(self):
        if self._running:
            return
        self._running = True
        self._eyes_closed_start = None
        self._eyes_closed_duration = 0.0
        self._yawn_timestamps.clear()
        self._yawn_cooldown = 0.0
        self._calibration_samples.clear()
        self._calibrated = False
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

        # Load Haar Cascade classifiers
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )

        cal_start = time.time()
        no_eyes_consecutive = 0  # Track frames where NO eyes detected (closed)
        mouth_open_consecutive = 0
        
        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    self.msleep(30)
                    continue

                # Resize and flip
                small = cv2.resize(frame, (640, 480))
                small = cv2.flip(small, 1)  # Mirror flip
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                
                # Detect faces
                faces = face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
                )
                
                current_time = time.time()
                eyes_closed = False
                ear_value = 0.0
                mar_value = 0.0

                if len(faces) > 0:
                    # Process first detected face
                    (x, y, w, h) = faces[0]
                    cv2.rectangle(small, (x, y), (x+w, y+h), (0, 255, 255), 2)
                    
                    face_gray = gray[y:y+h, x:x+w]
                    face_color = small[y:y+h, x:x+w]
                    
                    # ── EYE DETECTION ────────────────────────────
                    # Detect eyes in upper 60% of face
                    eye_region_gray = face_gray[0:int(h*0.6), :]
                    eye_region_color = face_color[0:int(h*0.6), :]
                    
                    eyes = eye_cascade.detectMultiScale(
                        eye_region_gray, scaleFactor=1.05, minNeighbors=3, 
                        minSize=(int(w*0.12), int(h*0.08))
                    )
                    
                    if len(eyes) >= 2:
                        # Eyes detected = OPEN
                        eyes_closed = False
                        no_eyes_consecutive = 0
                        
                        for (ex, ey, ew, eh) in eyes[:2]:
                            cv2.rectangle(eye_region_color, (ex, ey), 
                                        (ex+ew, ey+eh), (0, 255, 0), 2)
                            eye_roi = eye_region_gray[ey:ey+eh, ex:ex+ew]
                            ear_value = max(ear_value, np.mean(eye_roi) / 255.0)
                        
                        # Calibration phase (collect baseline EAR)
                        if not self._calibrated:
                            if current_time - cal_start < 2.0:
                                self._calibration_samples.append(ear_value)
                            elif len(self._calibration_samples) > 5:
                                baseline = np.mean(list(self._calibration_samples))
                                self._ear_threshold = baseline * 0.75
                                self._calibrated = True
                                self.calibration_complete.emit(self._ear_threshold)
                            else:
                                self._ear_threshold = 0.18
                                self._calibrated = True
                                self.calibration_complete.emit(self._ear_threshold)
                    else:
                        # No eyes detected = likely CLOSED
                        no_eyes_consecutive += 1
                        ear_value = 0.0
                        
                        # After 3 consecutive frames with no eyes → confirm closed
                        if no_eyes_consecutive >= 3:
                            eyes_closed = True
                        
                        # Mark eye region in red when closed
                        if eyes_closed:
                            ey_top = int(h * 0.2)
                            ey_bot = int(h * 0.45)
                            ex_left = int(w * 0.15)
                            ex_right = int(w * 0.85)
                            cv2.rectangle(face_color, (ex_left, ey_top),
                                        (ex_right, ey_bot), (0, 0, 255), 2)
                            cv2.putText(small, "EYES CLOSED", (x, y - 10),
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    
                    # ── YAWN DETECTION (dark-pixel analysis) ─────
                    # Extract lower face region (mouth area)
                    mouth_y_start = int(h * 0.6)
                    mouth_x_start = int(w * 0.25)
                    mouth_x_end = int(w * 0.75)
                    mouth_region = face_gray[mouth_y_start:, mouth_x_start:mouth_x_end]
                    mouth_region_color_roi = face_color[mouth_y_start:, mouth_x_start:mouth_x_end]
                    
                    if mouth_region.size > 0:
                        # Threshold to find dark pixels (inside of open mouth)
                        # Increased from 60 to 70 for better mouth detection in various lighting
                        _, binary = cv2.threshold(mouth_region, 70, 255, cv2.THRESH_BINARY_INV)
                        dark_ratio = np.sum(binary > 0) / binary.size
                        
                        # Find largest dark contour (open mouth)
                        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, 
                                                       cv2.CHAIN_APPROX_SIMPLE)
                        
                        if contours:
                            largest = max(contours, key=cv2.contourArea)
                            area = cv2.contourArea(largest)
                            mouth_area = mouth_region.shape[0] * mouth_region.shape[1]
                            
                            if mouth_area > 0:
                                mar_value = area / mouth_area  # Ratio of dark area
                            
                            # Draw mouth contour
                            if mar_value > 0.12:  # Lowered from 0.15 to show visualization earlier
                                bx, by, bw, bh = cv2.boundingRect(largest)
                                cv2.rectangle(mouth_region_color_roi, (bx, by),
                                            (bx+bw, by+bh), (0, 0, 255), 2)
                        
                        # Detect yawn: large dark area = mouth wide open
                        # Lowered threshold from 0.25 to 0.15 for better sensitivity
                        if mar_value > 0.15:
                            mouth_open_consecutive += 1
                            # Reduced from 5 to 3 consecutive frames for more responsive detection
                            if mouth_open_consecutive >= 3 and self._yawn_cooldown <= 0:
                                # Yawn confirmed after 3+ consecutive frames
                                self._yawn_timestamps.append(current_time)
                                self._yawn_cooldown = 2.0  # 2 second cooldown
                                cv2.putText(small, "YAWN DETECTED!", (x, y+h+30),
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                                mouth_open_consecutive = 0
                        else:
                            mouth_open_consecutive = 0
                    
                    # Display metrics on frame
                    ear_color = (0, 0, 255) if eyes_closed else (0, 255, 0)
                    mar_color = (0, 0, 255) if mar_value > 0.15 else (0, 255, 0)  # Updated threshold
                    cv2.putText(small, f"EAR: {ear_value:.2f}", (10, 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, ear_color, 2)
                    cv2.putText(small, f"MAR: {mar_value:.2f}", (10, 60),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, mar_color, 2)
                else:
                    # No face detected
                    no_eyes_consecutive = 0
                    mouth_open_consecutive = 0
                
                # Decrease yawn cooldown
                if self._yawn_cooldown > 0:
                    self._yawn_cooldown -= 0.033
                
                # Track eyes closed duration
                if eyes_closed and len(faces) > 0:
                    if self._eyes_closed_start is None:
                        self._eyes_closed_start = current_time
                    self._eyes_closed_duration = current_time - self._eyes_closed_start
                else:
                    self._eyes_closed_start = None
                    self._eyes_closed_duration = 0.0

                # Calculate yawns per minute (last 60 seconds)
                cutoff_time = current_time - 60.0
                recent_yawns = [t for t in self._yawn_timestamps if t > cutoff_time]
                yawns_per_min = len(recent_yawns)

                # Emit detection data
                self.detection_update.emit(
                    self._eyes_closed_duration,
                    float(yawns_per_min),
                    ear_value,
                    mar_value
                )

                # Emit preview frame
                display = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                qh, qw, ch = display.shape
                bpl = ch * qw
                qimg = QImage(
                    display.tobytes(), qw, qh, bpl, QImage.Format.Format_RGB888
                )
                self.frame_ready.emit(qimg.copy())

                self.msleep(33)  # ~30 fps
                
        finally:
            cap.release()
            self._running = False
            self._eyes_closed_start = None
            self._eyes_closed_duration = 0.0
            self.status_changed.emit("Stopped")
