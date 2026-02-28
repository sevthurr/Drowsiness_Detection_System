"""Camera-based drowsiness detection using OpenCV."""

import time
import cv2
import numpy as np
from collections import deque
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class CameraDetector(QThread):
    """Captures camera frames, detects face/eyes/yawns using OpenCV, emits drowsiness data.
    
    Yawn Detection Logic:
    ---------------------
    Uses percentile-based adaptive detection for reliable mouth opening detection:
    
    1. **Percentile Thresholding**: Automatically finds the darkest 25% of pixels in 
       the mouth region, adapting to any lighting condition without fixed thresholds.
       
    2. **Duration Requirement**: Mouth must be open for 5-7 seconds to count as a yawn,
       preventing false positives from talking or brief mouth openings.
       
    3. **Shape Validation**: Checks contour dimensions, aspect ratio, and area to 
       ensure genuine mouth opening (not shadows or artifacts).
       
    4. **Alert Threshold**: More than 1 yawn per minute (threshold of 2) triggers 
       drowsiness alerts based on medical indicators of excessive yawning.
    """

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
        self._yawn_timestamps = deque(maxlen=500)  # Track more yawns for 15-minute window
        self._yawn_cooldown = 0.0
        self._mouth_open_frames = 0
        self._last_yawn_time = 0.0
        self._mouth_open_start = None  # Track when mouth opening began
        self._yawn_registered = False  # Prevent multiple registrations per yawn
        
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
        self._mouth_open_start = None
        self._yawn_registered = False
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
                        # Calculate mean and std of mouth region brightness
                        mean_brightness = np.mean(mouth_region)
                        std_brightness = np.std(mouth_region)
                        
                        # Simple percentile-based thresholding - finds darkest pixels
                        # This works well across different lighting conditions
                        threshold_value = np.percentile(mouth_region, 25)  # Bottom 25% darkest pixels
                        threshold_value = max(40, min(100, int(threshold_value)))  # Clamp between 40-100
                        
                        # Apply threshold to find dark regions (open mouth interior)
                        _, binary = cv2.threshold(mouth_region, threshold_value, 255, cv2.THRESH_BINARY_INV)
                        
                        # Apply morphological operations to clean up noise
                        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
                        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
                        
                        # Find contours
                        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        
                        # Initialize variables
                        bx, by, bw, bh = 0, 0, 0, 0
                        contour_aspect_ratio = 0
                        
                        if contours and len(contours) > 0:
                            # Filter contours by minimum area
                            valid_contours = [c for c in contours if cv2.contourArea(c) > 30]
                            
                            if valid_contours:
                                largest = max(valid_contours, key=cv2.contourArea)
                                area = cv2.contourArea(largest)
                                mouth_area = mouth_region.shape[0] * mouth_region.shape[1]
                                
                                if mouth_area > 0:
                                    mar_value = area / mouth_area  # Ratio of dark area
                                    
                                    # Get bounding box dimensions
                                    bx, by, bw, bh = cv2.boundingRect(largest)
                                    contour_aspect_ratio = bw / bh if bh > 0 else 0
                                    
                                    # Draw mouth contour for visualization
                                    if mar_value > 0.10:
                                        cv2.rectangle(mouth_region_color_roi, (bx, by),
                                                    (bx+bw, by+bh), (0, 0, 255), 2)
                        
                        # Detect mouth opening with simpler, more reliable criteria
                        min_mouth_height = int(mouth_region.shape[0] * 0.15)
                        
                        # Adaptive MAR threshold based on brightness variability
                        # High std = varied lighting/shadows, need higher threshold
                        if std_brightness > 30:
                            mar_threshold = 0.25  # High variation - stricter
                        elif mean_brightness < 60:
                            mar_threshold = 0.28  # Dark - stricter to avoid shadows
                        else:
                            mar_threshold = 0.20  # Normal lighting
                        
                        is_mouth_open = (
                            mar_value > mar_threshold and  # Adaptive threshold
                            bh > min_mouth_height and      # Vertical opening significant
                            contour_aspect_ratio > 0.8 and # Roughly horizontal
                            bh > 5 and                     # Absolute minimum height
                            bw > 10                        # Minimum width
                        )
                        
                        if is_mouth_open:
                            # Start tracking if mouth just opened
                            if self._mouth_open_start is None:
                                self._mouth_open_start = current_time
                                self._yawn_registered = False
                            
                            # Calculate how long mouth has been open
                            mouth_open_duration = current_time - self._mouth_open_start
                            
                            # Check if duration is in valid yawn range (5-7 seconds)
                            if 5.0 <= mouth_open_duration <= 7.0 and not self._yawn_registered:
                                # Valid yawn detected!
                                self._yawn_timestamps.append(current_time)
                                self._last_yawn_time = current_time
                                self._yawn_registered = True  # Prevent counting same yawn multiple times
                                cv2.putText(small, "YAWN DETECTED!", (x, y+h+30),
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                            
                            # Show duration while mouth is open
                            if mouth_open_duration < 5.0:
                                cv2.putText(small, f"Mouth open: {mouth_open_duration:.1f}s", (x, y+h+30),
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                            elif mouth_open_duration > 7.0:
                                # Reset if held too long (probably talking/eating)
                                self._mouth_open_start = None
                                self._yawn_registered = False
                        else:
                            # Mouth closed - reset tracking
                            self._mouth_open_start = None
                            self._yawn_registered = False
                            mouth_open_consecutive = 0
                    
                    # Display metrics on frame
                    ear_color = (0, 0, 255) if eyes_closed else (0, 255, 0)
                    mar_color = (0, 0, 255) if mar_value > 0.20 else (0, 255, 0)  # Approximate threshold
                    cv2.putText(small, f"EAR: {ear_value:.2f}", (10, 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, ear_color, 2)
                    cv2.putText(small, f"MAR: {mar_value:.2f}", (10, 60),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, mar_color, 2)
                else:
                    # No face detected - reset all tracking
                    no_eyes_consecutive = 0
                    mouth_open_consecutive = 0
                    self._mouth_open_start = None
                    self._yawn_registered = False
                
                # Track eyes closed duration
                if eyes_closed and len(faces) > 0:
                    if self._eyes_closed_start is None:
                        self._eyes_closed_start = current_time
                    self._eyes_closed_duration = current_time - self._eyes_closed_start
                else:
                    self._eyes_closed_start = None
                    self._eyes_closed_duration = 0.0

                # Calculate yawns in different time windows
                # 1-minute window: >1 yawn per minute is excessive (intensity check)
                cutoff_1min = current_time - 60.0
                yawns_last_minute = [t for t in self._yawn_timestamps if t > cutoff_1min]
                yawns_per_min = len(yawns_last_minute)
                
                # 15-minute window: >3 yawns in 15 minutes indicates sleepiness (frequency check)
                cutoff_15min = current_time - 900.0  # 15 minutes = 900 seconds
                yawns_last_15min = [t for t in self._yawn_timestamps if t > cutoff_15min]
                yawns_in_15min = len(yawns_last_15min)
                
                # Emit detection data with actual yawn count (not multiplied)
                # Display shows actual yawns in last 60 seconds for user clarity
                # Alert logic will handle threshold evaluation separately
                self.detection_update.emit(
                    self._eyes_closed_duration,
                    float(yawns_per_min),  # Actual yawns in last minute
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
