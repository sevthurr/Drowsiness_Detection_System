"""Simulator engine — emulates Arduino alert logic at 10 Hz."""

from PySide6.QtCore import QObject, QTimer, Signal
from core.settings import DEFAULTS


class SimulatorEngine(QObject):
    """Runs alert-rule evaluation at 10 Hz and emits state dicts."""

    state_updated = Signal(dict)

    def __init__(self, settings, event_log, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.event_log = event_log
        self._running = False

        # Timer (10 Hz)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)

        # --- external inputs ---
        self._tilt_deg: float = 0.0
        self._force_eyes_closed: bool = False
        self._manual_yawns: float = 0.0

        # --- camera inputs ---
        self._cam_eyes_closed_s: float = 0.0
        self._cam_yawns: float = 0.0
        self._cam_running: bool = False

        # --- internal state ---
        self._tilt_over_s: float = 0.0
        self._sim_eyes_s: float = 0.0
        self._alert_level: str = "OK"
        self._alert_reason: str = ""
        self._is_critical: bool = False
        self._ack_remaining: float = 0.0
        self._alert_active: bool = False

        self._vibration_on: bool = False
        self._buzzer_on: bool = False
        self._alarm_playing: bool = False

    # ── public API ──────────────────────────────────────────────────
    def start(self):
        if self._running:
            return
        self._running = True
        self._reset()
        self._timer.start()
        self.event_log.add("Simulation started", "info")
        self._emit()

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self._reset()
        self._emit()
        self.event_log.add("Simulation stopped", "info")

    @property
    def running(self) -> bool:
        return self._running

    def set_tilt(self, deg: float):
        self._tilt_deg = deg

    def set_force_eyes_closed(self, on: bool):
        self._force_eyes_closed = on
        if not on:
            self._sim_eyes_s = 0.0

    def set_manual_yawns(self, val: float):
        self._manual_yawns = val

    def update_camera(self, eyes_s: float, yawns: float):
        self._cam_eyes_closed_s = eyes_s
        self._cam_yawns = yawns

    def set_camera_running(self, on: bool):
        self._cam_running = on
        if not on:
            self._cam_eyes_closed_s = 0.0
            self._cam_yawns = 0.0

    def acknowledge(self):
        if self._alert_level == "OK":
            return
        self.event_log.add("Acknowledge pressed — alert cleared", "info")
        self._alert_level = "OK"
        self._alert_reason = ""
        self._is_critical = False
        self._ack_remaining = 0.0
        self._alert_active = False
        self._tilt_over_s = 0.0
        self._sim_eyes_s = 0.0
        self._vibration_on = False
        self._buzzer_on = False
        self._alarm_playing = False
        self._emit()

    # ── internals ───────────────────────────────────────────────────
    def _reset(self):
        self._tilt_over_s = 0.0
        self._sim_eyes_s = 0.0
        self._alert_level = "OK"
        self._alert_reason = ""
        self._is_critical = False
        self._ack_remaining = 0.0
        self._alert_active = False
        self._vibration_on = False
        self._buzzer_on = False
        self._alarm_playing = False

    def _th(self):
        """Return effective thresholds (override vs defaults)."""
        use_override = self.settings.get("thresholds_override", False)
        src = self.settings if use_override else type("D", (), {"get": lambda s, k, d=None: DEFAULTS.get(k, d)})()
        return {
            "tilt_deg": float(src.get("tilt_threshold_deg", 30)),
            "tilt_dur": float(src.get("tilt_duration_s", 3)),
            "eyes_s": float(src.get("eyes_closed_threshold_s", 2)),
            "eyes_crit": float(src.get("eyes_critical_s", 4)),
            "yawns": float(src.get("yawns_per_min_threshold", 3)),
            "ack_t": float(src.get("acknowledge_timeout_s", 10)),
        }

    def _tick(self):
        dt = 0.1
        th = self._th()

        # ── compute effective inputs ─────────────────────────────
        # Tilt
        if self._tilt_deg > th["tilt_deg"]:
            self._tilt_over_s += dt
        else:
            self._tilt_over_s = 0.0

        # Eyes closed
        if self._force_eyes_closed:
            self._sim_eyes_s += dt
            eff_eyes = self._sim_eyes_s
        elif self._cam_running:
            eff_eyes = self._cam_eyes_closed_s
            self._sim_eyes_s = 0.0
        else:
            eff_eyes = 0.0
            self._sim_eyes_s = 0.0

        # Yawns
        if self._cam_running:
            eff_yawns = max(self._cam_yawns, self._manual_yawns)
        else:
            eff_yawns = self._manual_yawns

        # ── alert rule evaluation ────────────────────────────────
        if self._alert_level != "MAX":
            # Level 2 check (eyes closed)
            if eff_eyes > th["eyes_s"]:
                if self._alert_level != "Level 2":
                    prev = self._alert_level
                    self._alert_level = "Level 2"
                    self._alert_reason = "Eyes Closed"
                    self._ack_remaining = th["ack_t"]
                    self._alert_active = True
                    self.event_log.add(
                        f"Level 2 triggered — eyes closed {eff_eyes:.1f}s",
                        "warning",
                    )
                if eff_eyes >= th["eyes_crit"] and not self._is_critical:
                    self._is_critical = True
                    self.event_log.add(
                        f"CRITICAL — eyes closed {eff_eyes:.1f}s", "critical"
                    )

            # Level 1 check (tilt or yawns) — only from OK
            elif self._alert_level == "OK":
                if self._tilt_over_s > th["tilt_dur"]:
                    self._alert_level = "Level 1"
                    self._alert_reason = "Tilt"
                    self._ack_remaining = th["ack_t"]
                    self._alert_active = True
                    self.event_log.add(
                        f"Level 1 triggered — tilt {self._tilt_deg:.0f}° for "
                        f"{self._tilt_over_s:.1f}s",
                        "warning",
                    )
                elif eff_yawns >= th["yawns"]:
                    self._alert_level = "Level 1"
                    self._alert_reason = "Yawn"
                    self._ack_remaining = th["ack_t"]
                    self._alert_active = True
                    self.event_log.add(
                        f"Level 1 triggered — {eff_yawns:.0f} yawns/min",
                        "warning",
                    )

            # Ack timeout → MAX
            if self._alert_active and self._alert_level in ("Level 1", "Level 2"):
                self._ack_remaining -= dt
                if self._ack_remaining <= 0:
                    self._ack_remaining = 0.0
                    self._alert_level = "MAX"
                    self._alert_active = True
                    self.event_log.add(
                        "MAX escalation — acknowledge timeout expired", "critical"
                    )

        # ── actuator states ──────────────────────────────────────
        if self._alert_level in ("Level 1", "Level 2", "MAX"):
            self._vibration_on = True
            self._buzzer_on = True
            self._alarm_playing = self._alert_level in ("Level 2", "MAX")
        else:
            self._vibration_on = False
            self._buzzer_on = False
            self._alarm_playing = False

        self._emit(eff_eyes, eff_yawns)

    def _emit(self, eyes: float = 0.0, yawns: float = 0.0):
        is_l2 = self._alert_level in ("Level 2", "MAX")
        vib_key = "vibration_freq_l2" if is_l2 else "vibration_freq_l1"
        state = {
            "tilt_deg": self._tilt_deg,
            "tilt_over_threshold_s": self._tilt_over_s,
            "eyes_closed_s": eyes,
            "yawns_per_min": yawns,
            "alert_level": self._alert_level,
            "alert_reason": self._alert_reason,
            "is_critical": self._is_critical,
            "ack_remaining_s": max(0.0, self._ack_remaining),
            "vibration_on": self._vibration_on,
            "vibration_freq": float(self.settings.get(vib_key, 2.0)),
            "buzzer_on": self._buzzer_on,
            "buzzer_freq": int(self.settings.get("buzzer_freq_hz", 2000)),
            "alarm_playing": self._alarm_playing,
            "alarm_track": int(self.settings.get("alarm_track", 1)),
            "alarm_volume": int(self.settings.get("alarm_volume", 15)),
            "running": self._running,
        }
        self.state_updated.emit(state)
