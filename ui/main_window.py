"""Main application window — nav sidebar + stacked pages."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.event_log import EventLog
from core.settings import Settings
from core.simulator import SimulatorEngine
from camera.detector import CameraDetector
from ui.theme import DARK, LIGHT, build_stylesheet
from ui.widgets.top_bar import TopBar
from ui.widgets.nav_sidebar import NavSidebar
from ui.widgets.monitoring_page import MonitoringPage
from ui.widgets.left_panel import LeftPanel
from ui.widgets.right_panel import RightPanel


class MainWindow(QMainWindow):
    """Single-window dashboard with left nav and page stack."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Driver Drowsiness Detection System")
        self.setMinimumSize(960, 560)
        self.resize(1200, 700)

        # ── core objects ────────────────────────────────────────────
        self.settings = Settings()
        self.event_log = EventLog()
        self.simulator = SimulatorEngine(self.settings, self.event_log)
        self.camera = CameraDetector()

        self._dark = self.settings.get("theme", "dark") == "dark"
        self._last_alert_level = "OK"
        self._alert_dialog_shown = False

        # ── central widget ──────────────────────────────────────────
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Nav sidebar (left, fixed 72 px)
        self.nav = NavSidebar()
        outer.addWidget(self.nav)

        # Right side: top bar + page stack
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self.top_bar = TopBar(dark=self._dark)
        right_lay.addWidget(self.top_bar)

        # ── page stack ──────────────────────────────────────────────
        self._stack = QStackedWidget()

        # Page 0: Live Monitoring (uses full width)
        self.monitoring = MonitoringPage()
        self._stack.addWidget(self.monitoring)

        # Page 1: Simulator (full width, no wrapper)
        self.sim_panel = LeftPanel()
        sim_scroll = QScrollArea()
        sim_scroll.setWidgetResizable(True)
        sim_scroll.setWidget(self.sim_panel)
        sim_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(sim_scroll)

        # Page 2: Settings (full width, no wrapper)
        self.settings_panel = RightPanel(self.settings)
        set_scroll = QScrollArea()
        set_scroll.setWidgetResizable(True)
        set_scroll.setWidget(self.settings_panel)
        set_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stack.addWidget(set_scroll)

        right_lay.addWidget(self._stack)
        outer.addWidget(right, 1)

        # ── wire everything ─────────────────────────────────────────
        self._connect()
        self._apply_theme()

    # ── helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _scrollable_page(widget, max_w=500):
        """Wrap *widget* in a horizontally-centred scroll area."""
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(24, 12, 24, 12)
        h.addStretch()
        widget.setMaximumWidth(max_w)
        h.addWidget(widget)
        h.addStretch()

        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(container)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return sa

    # ── signal wiring ───────────────────────────────────────────────
    def _connect(self):
        sp = self.sim_panel
        mp_ = self.monitoring
        rp = self.settings_panel
        sim = self.simulator
        cam = self.camera
        log = self.event_log

        # Nav → page stack
        self.nav.page_changed.connect(self._stack.setCurrentIndex)

        # Simulator panel → engine
        sp.start_requested.connect(self._on_sim_start)
        sp.stop_requested.connect(self._on_sim_stop)
        sp.tilt_changed.connect(sim.set_tilt)
        sp.force_eyes_closed_changed.connect(sim.set_force_eyes_closed)
        sp.manual_yawns_changed.connect(sim.set_manual_yawns)

        # Camera → monitoring page
        cam.frame_ready.connect(mp_.update_camera_frame)
        cam.detection_update.connect(self._on_cam_detect)
        cam.calibration_complete.connect(self._on_calibration)
        cam.status_changed.connect(mp_.on_camera_status)

        # Monitoring page camera toggle
        mp_.camera_toggled.connect(self._on_camera_toggle)

        # Simulator engine → UI
        sim.state_updated.connect(mp_.update_state)
        sim.state_updated.connect(self.top_bar.update_state)
        sim.state_updated.connect(self._on_alert_check)

        # Event log → monitoring page
        log.entry_added.connect(mp_.add_log_entry)

        # Top bar theme toggle
        self.top_bar.theme_toggled.connect(self._on_theme)

        # Settings panel
        rp.settings_changed.connect(self._on_setting)
        rp.test_buzzer.connect(self._test_buzz)
        rp.test_vibration.connect(self._test_vib)
        rp.test_alarm.connect(self._test_alarm)

    # ── camera ──────────────────────────────────────────────────────
    def _on_camera_toggle(self, on):
        if on:
            self.camera.start_capture()
            self.simulator.set_camera_running(True)
        else:
            self.camera.stop_capture()
            self.simulator.set_camera_running(False)

    def _on_cam_detect(self, eyes_s, yawns, ear, mar):
        self.simulator.update_camera(eyes_s, yawns)

    def _on_calibration(self, threshold):
        self.event_log.add(
            f"Calibration complete \u2014 EAR threshold: {threshold:.3f}", "info"
        )


    # ── simulation control handlers ──────────────────────────────
    def _on_sim_start(self):
        """Reset alert state when simulation starts."""
        self._last_alert_level = "OK"
        self._alert_dialog_shown = False
        self.simulator.start()

    def _on_sim_stop(self):
        """Reset alert state when simulation stops."""
        self._last_alert_level = "OK"
        self._alert_dialog_shown = False
        self.simulator.stop()

    # ── alert popup ──────────────────────────────────────────
    def _on_alert_check(self, state):
        """Show popup dialog when drowsiness alert is triggered."""
        level = state.get("alert_level", "OK")
        
        # Show dialog when transitioning to Level 2 or MAX
        if level in ["Level 2", "MAX"] and self._last_alert_level not in ["Level 2", "MAX"]:
            if not self._alert_dialog_shown:
                self._alert_dialog_shown = True
                self._show_drowsiness_alert(level)
        elif level == "OK":
            self._alert_dialog_shown = False
        
        self._last_alert_level = level

    def _show_drowsiness_alert(self, level):
        """Display large popup asking to acknowledge drowsiness alarm."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.NoIcon)  # Remove icon to save space
        msg.setWindowTitle("Drowsiness Alert")
        
        # Theme-aware colors
        if self._dark:
            heading_color = "#ffffff"
            text_color = "#e6edf3"
            bg_color = "#0d1117"
            btn_bg = "#00bcd4"
            btn_hover = "#26c6da"
        else:
            heading_color = "#24292f"
            text_color = "#24292f"
            bg_color = "#ffffff"
            btn_bg = "#0097a7"
            btn_hover = "#00838f"
        
        # Large, bold text for driver visibility
        msg.setText(f"<h1 style='color:{heading_color}; font-size:36px; margin-bottom:20px;'>Drowsiness Alert Triggered!</h1>")
        msg.setInformativeText(
            f"<p style='font-size:18px; color:{text_color}; margin-bottom:15px;'>Alert Level: <b>{level}</b></p>"
            f"<p style='font-size:16px; color:{text_color};'>Do you want to acknowledge and turn off the alarm?</p>"
        )
        
        # Custom centered button
        msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
        btn = msg.addButton("Turn off Alarm", QMessageBox.ButtonRole.AcceptRole)
        
        # Make dialog box-shaped with theme-aware styling
        msg.setStyleSheet(f"""
            QMessageBox {{
                min-width: 650px;
                max-width: 650px;
                min-height: 450px;
                background-color: {bg_color};
            }}
            QMessageBox QLabel {{
                color: {text_color};
                min-width: 400px;
                max-width: 400px;
            }}
            QMessageBox QPushButton {{
                min-width: 140px;
                min-height: 40px;
                font-size: 16px;
                font-weight: bold;
                background-color: {btn_bg};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                margin-top: 10px;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {btn_hover};
            }}
        """)
        
        result = msg.exec()
        if result == QMessageBox.StandardButton.Ok:
            self.simulator.acknowledge()
            self.event_log.add("Alarm acknowledged by user", "info")
            self._alert_dialog_shown = False
    # ── theme ───────────────────────────────────────────────────────
    def _on_theme(self, dark):
        self._dark = dark
        self.settings.set("theme", "dark" if dark else "light")
        self._apply_theme()
        # Update monitoring page theme for camera button
        self.monitoring.set_theme(dark)

    def _apply_theme(self):
        colours = DARK if self._dark else LIGHT
        self.setStyleSheet(build_stylesheet(colours))

    # ── settings / tests ────────────────────────────────────────────
    def _on_setting(self, key, value):
        self.event_log.add(f"Setting changed: {key} = {value}", "info")

    def _test_buzz(self):
        hz = self.settings.get("buzzer_freq_hz", 2000)
        self.event_log.add(f"Test buzzer at {hz} Hz", "info")
        self.monitoring.show_actuator("buzz", f"Buzzer beep ({hz} Hz)", 2500)

    def _test_vib(self):
        f = self.settings.get("vibration_freq_l1", 2.0)
        self.event_log.add(f"Test vibration at {f} p/s", "info")
        self.monitoring.show_actuator("vib", f"Vibration ON ({f} p/s)", 2500)

    def _test_alarm(self):
        t = self.settings.get("alarm_track", 1)
        v = self.settings.get("alarm_volume", 15)
        self.event_log.add(f"Test alarm \u2014 track {t:03d}, vol {v}", "info")
        self.monitoring.show_actuator(
            "alarm", f"Alarm track {t:03d} playing (vol {v})", 2500
        )

    # ── cleanup ─────────────────────────────────────────────────────
    def closeEvent(self, event):
        self.camera.stop_capture()
        self.simulator.stop()
        super().closeEvent(event)
