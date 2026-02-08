"""Live monitoring page — camera preview, metrics, alert banner, event log."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.cards import Card, MetricCard


class MonitoringPage(QWidget):
    """Main dashboard page: camera feed + metrics + event log."""

    camera_toggled = Signal(bool)       # True = turn on

    def __init__(self, parent=None):
        super().__init__(parent)
        self._camera_on = False
        self._is_dark_theme = True
        self._build()

    # ── build ───────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(10)

        # ── main area: camera (left, larger) + metrics (right) ──
        main = QHBoxLayout()
        main.setSpacing(14)

        # Left: Camera preview card with button below
        cam_container = QVBoxLayout()
        cam_container.setSpacing(8)
        
        cam_card = Card()
        cam_lay = QVBoxLayout(cam_card)
        cam_lay.setContentsMargins(8, 8, 8, 8)
        self._preview = QLabel("Camera Off")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(480, 360)
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._preview.setStyleSheet(
            "background:#000000; border-radius:8px; color:#8b949e; font-size:14px;"
        )
        cam_lay.addWidget(self._preview)
        cam_container.addWidget(cam_card)
        
        # Camera toggle button below preview
        self._cam_btn = QPushButton("Camera OFF")
        self._cam_btn.setFixedHeight(40)
        self._cam_btn.setCheckable(True)
        self._cam_btn.toggled.connect(self._on_cam_toggle)
        self._style_cam_btn(False)
        cam_container.addWidget(self._cam_btn)
        
        main.addLayout(cam_container, 5)

        # Right: Metrics grid
        met_card = Card()
        grid = QGridLayout(met_card)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(10)

        self.m_eyes = MetricCard("Eyes Closed (s)", "0.0")
        self.m_yawns = MetricCard("Yawns / min", "0")
        self.m_tilt = MetricCard("Tilt (\u00b0)", "0")
        self.m_tilt_dur = MetricCard("Tilt > Thresh (s)", "0.0")
        self.m_alert = MetricCard("Alert Level", "OK")
        self.m_ack = MetricCard("Ack Timer (s)", "\u2014")

        grid.addWidget(self.m_eyes, 0, 0)
        grid.addWidget(self.m_yawns, 0, 1)
        grid.addWidget(self.m_tilt, 1, 0)
        grid.addWidget(self.m_tilt_dur, 1, 1)
        grid.addWidget(self.m_alert, 2, 0)
        grid.addWidget(self.m_ack, 2, 1)

        # Actuator status label below metrics
        self._actuator_lbl = QLabel("")
        self._actuator_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._actuator_lbl.setWordWrap(True)
        self._actuator_lbl.setStyleSheet("font-size:11px;")
        grid.addWidget(self._actuator_lbl, 3, 0, 1, 2)

        main.addWidget(met_card, 3)
        root.addLayout(main)

        # ── event log (smaller, below camera) ──────────────────
        log_hdr = QLabel("Event Log")
        log_hdr.setStyleSheet("font-size:12px; font-weight:600; margin-top:4px;")
        root.addWidget(log_hdr)

        self._log_list = QListWidget()
        self._log_list.setMaximumHeight(120)
        root.addWidget(self._log_list)

    # ── public slots ────────────────────────────────────────────────
    def update_camera_frame(self, qimg):
        pix = QPixmap.fromImage(qimg)
        self._preview.setPixmap(
            pix.scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def update_state(self, s):
        level = s.get("alert_level", "OK")
        eyes = s.get("eyes_closed_s", 0.0)
        yawns = s.get("yawns_per_min", 0.0)
        tilt = s.get("tilt_deg", 0.0)
        tilt_d = s.get("tilt_over_threshold_s", 0.0)
        ack = s.get("ack_remaining_s", 0.0)
        crit = s.get("is_critical", False)
        reason = s.get("alert_reason", "")

        self.m_eyes.set_value(f"{eyes:.1f}", "#f85149" if eyes > 2.0 else None)
        self.m_yawns.set_value(f"{yawns:.0f}")
        self.m_tilt.set_value(f"{tilt:.0f}")
        self.m_tilt_dur.set_value(f"{tilt_d:.1f}")

        lvl_colors = {
            "OK": "#3fb950",
            "Level 1": "#d29922",
            "Level 2": "#f85149",
            "MAX": "#ff2020",
        }
        self.m_alert.set_value(level, lvl_colors.get(level))
        self.m_ack.set_value(f"{ack:.1f}" if ack > 0 else "\u2014")

        # (Alert banner removed - now handled by popup dialog in main_window)

        # Actuator indicators
        acts = []
        if s.get("vibration_on"):
            acts.append(f"Vibration ({s.get('vibration_freq', 0):.1f} p/s)")
        if s.get("buzzer_on"):
            acts.append(f"Buzzer ({s.get('buzzer_freq', 0)} Hz)")
        if s.get("alarm_playing"):
            acts.append(
                f"Alarm #{s.get('alarm_track', 1):03d} (vol {s.get('alarm_volume', 0)})"
            )
        self._actuator_lbl.setText("  |  ".join(acts))

    def add_log_entry(self, ts, message, level):
        colors = {"info": "#8b949e", "warning": "#d29922", "critical": "#f85149"}
        item = QListWidgetItem(f"[{ts}]  {message}")
        item.setForeground(QColor(colors.get(level, "#8b949e")))
        self._log_list.insertItem(0, item)
        while self._log_list.count() > 200:
            self._log_list.takeItem(self._log_list.count() - 1)

    def show_actuator(self, kind, text, duration_ms=2000):
        self._actuator_lbl.setText(text)
        QTimer.singleShot(duration_ms, lambda: self._actuator_lbl.setText(""))

    def on_camera_status(self, status):
        if status == "Stopped":
            self._preview.clear()
            self._preview.setText("Camera Off")
            self._cam_btn.blockSignals(True)
            self._cam_btn.setChecked(False)
            self._cam_btn.blockSignals(False)
            self._style_cam_btn(False)
        elif status == "Running":
            self._style_cam_btn(True)
        elif status == "Error":
            self._preview.clear()
            self._preview.setText("Camera Error — check device")
            self._cam_btn.blockSignals(True)
            self._cam_btn.setChecked(False)
            self._cam_btn.blockSignals(False)
            self._style_cam_btn(False)

    # ── private ─────────────────────────────────────────────────────
    def _on_cam_toggle(self, checked):
        self._camera_on = checked
        self._style_cam_btn(checked)
        self.camera_toggled.emit(checked)

    def _style_cam_btn(self, on):
        if on:
            self._cam_btn.setText("Camera ON")
            self._cam_btn.setStyleSheet(
                "background:#3fb950; color:#ffffff; border:none; "
                "border-radius:8px; font-weight:bold; font-size:13px;"
            )
        else:
            self._cam_btn.setText("Camera OFF")
            # Theme-aware: dark background for dark mode, lighter for light mode
            if self._is_dark_theme:
                bg_color = "#30363d"
                text_color = "#8b949e"
            else:
                bg_color = "#d0d7de"
                text_color = "#656d76"
            self._cam_btn.setStyleSheet(
                f"background:{bg_color}; color:{text_color}; border:none; "
                "border-radius:8px; font-weight:bold; font-size:13px;"
            )

    def set_theme(self, is_dark):
        """Update theme state and refresh camera button style."""
        self._is_dark_theme = is_dark
        self._style_cam_btn(self._camera_on)

