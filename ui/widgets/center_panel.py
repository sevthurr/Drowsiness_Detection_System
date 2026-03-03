"""Centre panel — camera preview, metrics, alert banner, event log."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.cards import Card, MetricCard


class CenterPanel(QWidget):
    """Live monitoring panel (centre column)."""

    camera_start_requested = Signal()
    camera_stop_requested = Signal()
    calibrate_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    # ── build UI ────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        title = QLabel("Live Monitoring")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        root.addWidget(title)

        # ── camera card ─────────────────────────────────────────────
        cam_card = Card()
        cam_lay = QVBoxLayout(cam_card)
        cam_lay.setContentsMargins(14, 10, 14, 10)
        cam_lay.setSpacing(8)

        self._cam_preview = QLabel("Camera Off")
        self._cam_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_preview.setFixedHeight(240)
        self._cam_preview.setStyleSheet(
            "background:#000000; border-radius:8px; color:#8b949e; font-size:14px;"
        )
        cam_lay.addWidget(self._cam_preview)

        btn_row = QHBoxLayout()
        self._btn_cam_start = QPushButton("Start Camera")
        self._btn_cam_stop = QPushButton("Stop Camera")
        self._btn_cam_stop.setEnabled(False)
        self._btn_calibrate = QPushButton("Calibrate")
        self._btn_calibrate.setEnabled(False)
        btn_row.addWidget(self._btn_cam_start)
        btn_row.addWidget(self._btn_cam_stop)
        btn_row.addWidget(self._btn_calibrate)
        cam_lay.addLayout(btn_row)

        self._btn_cam_start.clicked.connect(self._on_cam_start)
        self._btn_cam_stop.clicked.connect(self._on_cam_stop)
        self._btn_calibrate.clicked.connect(self.calibrate_requested)

        root.addWidget(cam_card)

        # ── metrics grid ────────────────────────────────────────────
        met_lbl = QLabel("Metrics")
        met_lbl.setStyleSheet("font-size:14px; font-weight:600;")
        root.addWidget(met_lbl)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.m_eyes = MetricCard("Eyes Closed (s)", "0.0")
        self.m_yawns = MetricCard("Yawns / 10 min", "0")
        self.m_tilt = MetricCard("Tilt (°)", "0")
        self.m_tilt_dur = MetricCard("Tilt Over Thresh (s)", "0.0")
        self.m_alert = MetricCard("Alert Level", "OK")
        self.m_ack = MetricCard("Ack Remaining (s)", "--")
        grid.addWidget(self.m_eyes, 0, 0)
        grid.addWidget(self.m_yawns, 0, 1)
        grid.addWidget(self.m_tilt, 1, 0)
        grid.addWidget(self.m_tilt_dur, 1, 1)
        grid.addWidget(self.m_alert, 2, 0)
        grid.addWidget(self.m_ack, 2, 1)
        root.addLayout(grid)

        # ── alert banner ────────────────────────────────────────────
        self._banner = QFrame()
        self._banner.setStyleSheet(
            "background:#1a2f1a; border-radius:14px; padding:14px;"
        )
        ban_lay = QVBoxLayout(self._banner)
        ban_lay.setContentsMargins(14, 10, 14, 10)
        ban_lay.setSpacing(4)

        self._banner_text = QLabel("System OK")
        self._banner_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner_text.setStyleSheet("font-size:16px; font-weight:bold;")
        self._banner_text.setWordWrap(True)
        ban_lay.addWidget(self._banner_text)

        self._actuator_lbl = QLabel("")
        self._actuator_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._actuator_lbl.setWordWrap(True)
        self._actuator_lbl.setStyleSheet("font-size:12px;")
        ban_lay.addWidget(self._actuator_lbl)

        root.addWidget(self._banner)

        # ── event log ───────────────────────────────────────────────
        log_lbl = QLabel("Event Log")
        log_lbl.setStyleSheet("font-size:14px; font-weight:600;")
        root.addWidget(log_lbl)

        self._log_list = QListWidget()
        self._log_list.setMinimumHeight(140)
        root.addWidget(self._log_list)

        root.addStretch()

    # ── public slots ────────────────────────────────────────────────
    def update_camera_frame(self, qimg: QImage):
        pix = QPixmap.fromImage(qimg)
        self._cam_preview.setPixmap(
            pix.scaled(
                self._cam_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def update_state(self, s: dict):
        level = s.get("alert_level", "OK")
        eyes = s.get("eyes_closed_s", 0.0)
        yawns = s.get("yawns_per_10min", 0.0)
        tilt = s.get("tilt_deg", 0.0)
        tilt_d = s.get("tilt_over_threshold_s", 0.0)
        ack = s.get("ack_remaining_s", 0.0)
        crit = s.get("is_critical", False)
        reason = s.get("alert_reason", "")

        # Metric cards
        self.m_eyes.set_value(
            f"{eyes:.1f}",
            "#f85149" if eyes > 2.0 else None,
        )
        self.m_yawns.set_value(f"{yawns:.0f}")
        self.m_tilt.set_value(f"{tilt:.0f}")
        self.m_tilt_dur.set_value(f"{tilt_d:.1f}")

        # Alert level card colour
        lvl_colors = {
            "OK": "#3fb950",
            "Level 1": "#d29922",
            "Level 2": "#f85149",
            "MAX": "#ff2020",
        }
        self.m_alert.set_value(level, lvl_colors.get(level))
        self.m_ack.set_value(f"{ack:.1f}" if ack > 0 else "--")

        # Alert banner
        if level == "OK":
            self._banner_text.setText("System OK")
            self._set_banner_bg("#1a2f1a")
        elif level == "Level 1":
            self._banner_text.setText(f"Level 1 — {reason}")
            self._set_banner_bg("#3a3217")
        elif level == "Level 2":
            tag = "  [CRITICAL]" if crit else ""
            self._banner_text.setText(f"Level 2 — {reason}{tag}")
            self._set_banner_bg("#3a1a1a")
        elif level == "MAX":
            self._banner_text.setText("MAX ALERT — Acknowledge Required!")
            self._set_banner_bg("#5a0a0a")

        # Actuator indicators
        acts: list[str] = []
        if s.get("vibration_on"):
            acts.append(f"Vibration ON ({s.get('vibration_freq', 0):.1f} p/s)")
        if s.get("buzzer_on"):
            acts.append(f"Buzzer beep ({s.get('buzzer_freq', 0)} Hz)")
        if s.get("alarm_playing"):
            acts.append(
                f"Alarm track {s.get('alarm_track', 1):03d} "
                f"(vol {s.get('alarm_volume', 0)})"
            )
        self._actuator_lbl.setText("  |  ".join(acts))

    def add_log_entry(self, ts: str, message: str, level: str):
        colours = {"info": "#8b949e", "warning": "#d29922", "critical": "#f85149"}
        colour = colours.get(level, "#8b949e")
        item = QListWidgetItem(f"[{ts}]  {message}")
        item.setForeground(__import__("PySide6.QtGui", fromlist=["QColor"]).QColor(colour))
        self._log_list.insertItem(0, item)
        # Cap list length
        while self._log_list.count() > 200:
            self._log_list.takeItem(self._log_list.count() - 1)

    def show_actuator(self, kind: str, text: str, duration_ms: int = 2000):
        """Briefly show actuator text (used by test buttons)."""
        self._actuator_lbl.setText(text)
        QTimer.singleShot(duration_ms, lambda: self._actuator_lbl.setText(""))

    def on_camera_status(self, status: str):
        if status == "Stopped":
            self._cam_preview.clear()
            self._cam_preview.setText("Camera Off")
            self._btn_cam_start.setEnabled(True)
            self._btn_cam_stop.setEnabled(False)
            self._btn_calibrate.setEnabled(False)
        elif status == "Running":
            self._btn_cam_start.setEnabled(False)
            self._btn_cam_stop.setEnabled(True)
            self._btn_calibrate.setEnabled(True)
        elif status == "Error":
            self._cam_preview.setText("Camera Error")
            self._btn_cam_start.setEnabled(True)
            self._btn_cam_stop.setEnabled(False)
            self._btn_calibrate.setEnabled(False)

    # ── private ─────────────────────────────────────────────────────
    def _set_banner_bg(self, colour: str):
        self._banner.setStyleSheet(
            f"background:{colour}; border-radius:14px; padding:14px;"
        )

    def _on_cam_start(self):
        self._btn_cam_start.setEnabled(False)
        self.camera_start_requested.emit()

    def _on_cam_stop(self):
        self._btn_cam_stop.setEnabled(False)
        self.camera_stop_requested.emit()
