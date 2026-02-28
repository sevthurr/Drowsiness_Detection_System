"""Camera-based drowsiness detection using OpenCV."""

import os
import time
import cv2
import numpy as np
from pathlib import Path
from collections import deque
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

# Folder that contains reference yawn images used for threshold calibration
_REFERENCES_DIR = Path(__file__).parent / "references"


class CameraDetector(QThread):
    """Captures camera frames, detects face/eyes/yawns using OpenCV, emits drowsiness data.

    Eye Closure Detection:
    ----------------------
    Uses the glasses-aware Haar cascade to locate eye regions, then applies a
    pupil-contrast check that works *without* calibration and *without* relying
    on absolute brightness:

      pupil_ratio = 5th-percentile(eye_ROI) / mean(eye_ROI)

    Open eye  → dark pupil present → 5th-pct is low  → ratio ≈ 0.1–0.4
    Closed eye → eyelid covers pupil → 5th-pct ≈ mean → ratio ≈ 0.6–0.9

    Threshold: ratio > 0.60 = eyes closed.
    Confirmed after 2 consecutive frames (~66 ms) for fast response.

    Yawn Detection:
    ---------------
    Uses OTSU thresholding on the histogram-equalized mouth ROI.  OTSU
    automatically picks the optimal dark/light split within the local region,
    so it is immune to global face brightness (backlight, dark rooms, etc.).
    MAR > 8 % + minimum height → mouth open.
    Mouth must stay open ≥ 2.5 s to register as a yawn, with an 8 s cooldown.
    """

    frame_ready = Signal(QImage)
    detection_update = Signal(float, float, float, float)  # eyes_closed_s, yawns/min, ear, mar
    calibration_complete = Signal(float)  # ear_threshold
    status_changed = Signal(str)  # "Running" / "Stopped" / "Error"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

        # Eye closure tracking
        self._eyes_closed_start    = None
        self._eyes_closed_duration = 0.0
        self._no_eye_frames        = 0   # consecutive frames without clear open eyes

        # Yawn tracking
        self._yawn_timestamps    = deque(maxlen=500)
        self._mouth_open_start   = None
        self._yawn_registered    = False
        self._last_yawn_time     = 0.0
        self._yawn_cooldown_s    = 8.0
        self._mouth_open_frames  = 0   # consecutive frames with mouth confirmed open

        # Calibrated mouth-open thresholds (overridden by reference images if available)
        self._mar_threshold  = 0.15   # dark-area fraction of mouth region
        self._min_h_ratio    = 0.22   # min bbox height / mouth_h
        self._min_w_ratio    = 0.30   # min bbox width  / mouth_w
        self._min_aspect     = 1.1    # min bbox width  / bbox height

        # Run calibration from reference yawn images
        self._calibrate_yawn_thresholds()

    # ── reference-image calibration ─────────────────────────────────
    def _calibrate_yawn_thresholds(self):
        """Analyse reference yawn images in camera/references/ and derive
        detection thresholds from real yawn data.

        For each image the same pipeline used in run() is applied:
          face detect → mouth ROI → histogram-equalise → OTSU → contours
        The measured MAR and bounding-box ratios from every successful
        detection are collected.  Thresholds are then set to 60 % of the
        minimum observed value so that yawns at least 60 % as obvious as
        the subtlest reference still register.

        Falls back to hardcoded defaults if the folder is missing, empty,
        or no face is detected in any image.
        """
        if not _REFERENCES_DIR.is_dir():
            return

        image_paths = [
            p for p in _REFERENCES_DIR.iterdir()
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")
        ]
        if not image_paths:
            return

        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        mar_vals, bh_ratios, bw_ratios = [], [], []

        for path in image_paths:
            img = cv2.imread(str(path))
            if img is None:
                continue

            # Resize so the face is comparable to live-camera size
            img = cv2.resize(img, (640, 480))
            gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray_eq = cv2.equalizeHist(gray)

            faces = face_cascade.detectMultiScale(
                gray_eq, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
            )
            if len(faces) == 0:
                continue

            (x, y, w, h) = faces[0]
            face_gray = gray[y:y+h,    x:x+w]
            face_eq   = gray_eq[y:y+h, x:x+w]

            # Same mouth ROI as in run()
            my0 = int(h * 0.60)
            my1 = int(h * 0.92)
            mx0 = int(w * 0.18)
            mx1 = int(w * 0.82)
            mouth_raw = face_gray[my0:my1, mx0:mx1]
            mouth_eq  = face_eq[my0:my1,   mx0:mx1]

            if mouth_raw.size == 0:
                continue

            mouth_h, mouth_w = mouth_raw.shape
            mouth_area = mouth_h * mouth_w

            # OTSU on equalized mouth region
            _, binary = cv2.threshold(
                mouth_eq, 0, 255,
                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,  k)

            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                continue

            valid = [c for c in contours if cv2.contourArea(c) > 40]
            if not valid:
                continue

            largest   = max(valid, key=cv2.contourArea)
            dark_area = cv2.contourArea(largest)
            mar       = dark_area / mouth_area
            _, _, bw_c, bh_c = cv2.boundingRect(largest)

            if mar < 0.05:   # skip if the image has a closed mouth
                continue

            mar_vals.append(mar)
            bh_ratios.append(bh_c / mouth_h)
            bw_ratios.append(bw_c / mouth_w)

        if not mar_vals:
            return  # calibration failed — keep defaults

        # Use 60 % of the minimum observed value as the live threshold.
        # This means a yawn only needs to be 60 % as obvious as the most
        # subtle reference to be detected, giving a comfortable margin.
        self._mar_threshold = float(np.min(mar_vals))   * 0.60
        self._min_h_ratio   = float(np.min(bh_ratios))  * 0.55
        self._min_w_ratio   = float(np.min(bw_ratios))  * 0.55
        # Aspect-ratio lower bound — reference yawns are always wider than tall
        aspect_refs = [
            bw / bh for bw, bh in zip(bw_ratios, bh_ratios) if bh > 0
        ]
        self._min_aspect = max(0.80, float(np.min(aspect_refs)) * 0.70)

        print(
            f"[YawnCalib] {len(mar_vals)} reference(s) processed.  "
            f"MAR≥{self._mar_threshold:.3f}  "
            f"minH≥{self._min_h_ratio:.3f}  "
            f"minW≥{self._min_w_ratio:.3f}  "
            f"aspect≥{self._min_aspect:.2f}"
        )

    # ── public API ──────────────────────────────────────────────────
    @property
    def running(self):
        return self._running

    def start_capture(self):
        if self._running:
            return
        self._running = True
        self._eyes_closed_start    = None
        self._eyes_closed_duration = 0.0
        self._no_eye_frames        = 0
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

        # Prefer the eyeglasses-aware cascade; fall back to standard if missing
        eye_cascade_path = cv2.data.haarcascades + 'haarcascade_eye_tree_eyeglasses.xml'
        eye_cascade = cv2.CascadeClassifier(eye_cascade_path)
        if eye_cascade.empty():
            eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_eye.xml'
            )

        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )

        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    self.msleep(30)
                    continue

                small = cv2.resize(frame, (640, 480))
                small = cv2.flip(small, 1)
                gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                # Equalise histogram for more consistent detection across lighting
                gray_eq = cv2.equalizeHist(gray)

                faces = face_cascade.detectMultiScale(
                    gray_eq, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
                )

                current_time = time.time()
                eyes_closed  = False
                ear_value    = 0.0
                mar_value    = 0.0

                if len(faces) > 0:
                    (x, y, w, h) = faces[0]
                    cv2.rectangle(small, (x, y), (x+w, y+h), (0, 255, 255), 2)

                    face_gray  = gray[y:y+h, x:x+w]      # raw gray (preserves brightness)
                    face_eq    = gray_eq[y:y+h, x:x+w]   # equalized (for cascade detection)
                    face_color = small[y:y+h, x:x+w]

                    # ── EYE DETECTION ────────────────────────────────────────
                    # Run cascade on equalized image for better detection
                    eye_roi_eq    = face_eq[0:int(h * 0.60), :]
                    eye_roi_raw   = face_gray[0:int(h * 0.60), :]  # raw for pupil analysis
                    eye_roi_color = face_color[0:int(h * 0.60), :]

                    eyes = eye_cascade.detectMultiScale(
                        eye_roi_eq,
                        scaleFactor=1.05,
                        minNeighbors=3,
                        minSize=(int(w * 0.10), int(h * 0.07)),
                    )

                    if len(eyes) >= 2:
                        # ── Pupil-contrast check ──────────────────────────
                        # When eyes are OPEN: a dark pupil is present in the ROI,
                        # so the 5th-percentile (near-minimum) pixel is very dark.
                        # When eyes are CLOSED: eyelid covers the pupil, the ROI is
                        # uniform skin-tone — 5th-percentile rises significantly.
                        # Ratio = p5 / mean:  low = open, high = closed.
                        pupil_ratios = []
                        for (ex, ey, ew, eh) in eyes[:2]:
                            cv2.rectangle(eye_roi_color, (ex, ey),
                                          (ex+ew, ey+eh), (0, 255, 0), 2)
                            roi = eye_roi_raw[ey:ey+eh, ex:ex+ew]
                            if roi.size > 0:
                                p5  = float(np.percentile(roi, 5))
                                mn  = float(np.mean(roi))
                                if mn > 0:
                                    pupil_ratios.append(p5 / mn)

                        ear_value = 1.0 - np.mean(pupil_ratios) if pupil_ratios else 0.5

                        # Pupil ratio > 0.60 means 5th-percentile is close to the
                        # mean → no dark pupil → eyelid is covering → eye CLOSED
                        if pupil_ratios and np.mean(pupil_ratios) > 0.60:
                            self._no_eye_frames += 1
                        else:
                            self._no_eye_frames = 0

                    else:
                        # Cascade found fewer than 2 eyes — treat as closed
                        self._no_eye_frames += 1
                        ear_value = 0.0

                    # Confirm closure after 2 consecutive frames (~66 ms) for fast response
                    eyes_closed = self._no_eye_frames >= 2

                    if eyes_closed:
                        ey_t = int(h * 0.12)
                        ey_b = int(h * 0.52)
                        cv2.rectangle(face_color,
                                      (int(w*0.08), ey_t),
                                      (int(w*0.92), ey_b),
                                      (0, 0, 255), 2)
                        cv2.putText(small, "EYES CLOSED",
                                    (x, y - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                    # ── YAWN DETECTION ───────────────────────────────────────
                    # Use lower portion of the face (below nose), stop before chin
                    my0 = int(h * 0.60)
                    my1 = int(h * 0.92)   # exclude chin — bottom ~8 % is jaw/shadow
                    mx0 = int(w * 0.18)
                    mx1 = int(w * 0.82)
                    mouth_raw   = face_gray[my0:my1, mx0:mx1]
                    mouth_eq    = face_eq[my0:my1,   mx0:mx1]
                    mouth_color = face_color[my0:my1, mx0:mx1]
                    otsu_thresh = 0.0   # initialised here so OT overlay always has a value

                    if mouth_raw.size > 0:
                        mouth_h, mouth_w = mouth_raw.shape
                        mouth_area = mouth_h * mouth_w

                        # Use OTSU thresholding on the LOCAL mouth region (equalized).
                        # OTSU automatically picks the best threshold to split dark vs light
                        # pixels within THIS region — immune to global face brightness changes.
                        #
                        # CRITICAL: the otsu_thresh value itself signals detection quality.
                        #   High otsu_thresh (≥ 40) → strong bimodal split → real dark cavity.
                        #   Low  otsu_thresh (<  40) → nearly uniform region → closed mouth;
                        #     any "dark" pixels are just lip-crease or shadow noise.
                        # We skip detection entirely when the split is too weak.
                        otsu_thresh, binary = cv2.threshold(
                            mouth_eq, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
                        )

                        # Gate 0: reject weak-contrast (closed-mouth) frames early
                        if otsu_thresh < 40:
                            bx = by = bw_c = bh_c = 0
                            mar_value = 0.0
                        else:
                            # Clean up noise
                            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
                            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,  k)

                            contours, _ = cv2.findContours(
                                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                            )

                            bx, by, bw_c, bh_c = 0, 0, 0, 0
                            if contours:
                                valid = [c for c in contours if cv2.contourArea(c) > 40]
                                if valid:
                                    largest   = max(valid, key=cv2.contourArea)
                                    dark_area = cv2.contourArea(largest)
                                    mar_value = dark_area / mouth_area

                                    bx, by, bw_c, bh_c = cv2.boundingRect(largest)

                                    # Gate 1: dark region must be in upper 70 % of mouth ROI.
                                    # A real open-mouth cavity sits between the lips (upper half).
                                    # Chin shadows appear near the bottom → reject them.
                                    region_center_y = by + bh_c // 2
                                    if region_center_y > mouth_h * 0.70:
                                        bx = by = bw_c = bh_c = 0
                                        mar_value = 0.0

                                    if mar_value >= self._mar_threshold:
                                        cv2.rectangle(mouth_color,
                                                      (bx, by), (bx+bw_c, by+bh_c),
                                                      (0, 165, 255), 2)

                        # ── Open-mouth gate (thresholds calibrated from reference images) ──
                        # A real wide-open mouth must satisfy ALL of:
                        #   1. Dark area ≥ _mar_threshold  of the mouth region
                        #   2. Bounding-box height  ≥ _min_h_ratio * mouth_h
                        #   3. Bounding-box width   ≥ _min_w_ratio * mouth_w
                        #   4. Aspect ratio bw/bh   ≥ _min_aspect
                        # Thin lip-crease / chin shadows fail one or more of these.
                        # Thresholds are derived from camera/references/ at startup;
                        # default to conservative hardcoded values if no references.
                        min_h     = int(mouth_h * self._min_h_ratio)
                        min_w     = int(mouth_w * self._min_w_ratio)
                        aspect_ok = (bh_c > 0) and (bw_c / bh_c >= self._min_aspect)
                        is_mouth_open = (
                            mar_value >= self._mar_threshold
                            and bh_c >= min_h
                            and bw_c >= min_w
                            and aspect_ok
                        )

                        # ── 4-frame debounce (~130 ms) before timer starts ────
                        # Prevents any single noisy frame from triggering the counter.
                        if is_mouth_open:
                            self._mouth_open_frames += 1
                        else:
                            self._mouth_open_frames = 0

                        mouth_confirmed = self._mouth_open_frames >= 4

                        # ── Yawn timing ──────────────────────────────────────
                        cooldown_ok = (current_time - self._last_yawn_time) >= self._yawn_cooldown_s

                        if mouth_confirmed:
                            if self._mouth_open_start is None:
                                self._mouth_open_start = current_time
                                self._yawn_registered  = False

                            mouth_open_dur = current_time - self._mouth_open_start

                            if mouth_open_dur >= 2.5 and not self._yawn_registered and cooldown_ok:
                                self._yawn_timestamps.append(current_time)
                                self._last_yawn_time  = current_time
                                self._yawn_registered = True
                                cv2.putText(small, "YAWN DETECTED!",
                                            (x, y + h + 35),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                            elif mouth_open_dur < 2.5:
                                cv2.putText(small,
                                            f"Mouth open: {mouth_open_dur:.1f}s",
                                            (x, y + h + 35),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                        else:
                            self._mouth_open_start  = None
                            self._yawn_registered   = False

                    # On-frame metrics
                    ear_col  = (0, 0, 255) if eyes_closed else (0, 255, 0)
                    mar_col  = (0, 0, 255) if mar_value >= self._mar_threshold else (0, 255, 0)
                    otsu_col = (0, 0, 255) if otsu_thresh < 40 else (0, 255, 0)
                    cv2.putText(small, f"EAR: {ear_value:.2f}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, ear_col, 2)
                    cv2.putText(small, f"MAR: {mar_value:.2f}", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, mar_col, 2)
                    cv2.putText(small, f"OT:  {int(otsu_thresh)}", (10, 90),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, otsu_col, 2)

                else:
                    # No face — reset all transient state
                    self._no_eye_frames     = 0
                    self._mouth_open_start  = None
                    self._yawn_registered   = False
                    self._mouth_open_frames = 0

                # ── Eye-closed duration tracking ─────────────────────────────
                if eyes_closed and len(faces) > 0:
                    if self._eyes_closed_start is None:
                        self._eyes_closed_start = current_time
                    self._eyes_closed_duration = current_time - self._eyes_closed_start
                else:
                    self._eyes_closed_start   = None
                    self._eyes_closed_duration = 0.0

                # ── Yawn rate calculation ─────────────────────────────────────
                cutoff_1min = current_time - 60.0
                yawns_per_min = sum(1 for t in self._yawn_timestamps if t > cutoff_1min)

                self.detection_update.emit(
                    self._eyes_closed_duration,
                    float(yawns_per_min),
                    ear_value,
                    mar_value,
                )

                # ── Emit preview frame ────────────────────────────────────────
                display = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                qh, qw, ch = display.shape
                qimg = QImage(
                    display.tobytes(), qw, qh, ch * qw, QImage.Format.Format_RGB888
                )
                self.frame_ready.emit(qimg.copy())

                self.msleep(33)  # ~30 fps

        finally:
            cap.release()
            self._running             = False
            self._eyes_closed_start   = None
            self._eyes_closed_duration = 0.0
            self.status_changed.emit("Stopped")
