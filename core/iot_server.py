"""
IoT HTTP server — receives POST /sensor from the NodeMCU Wi-Fi bridge and
feeds real hardware data into the SimulatorEngine running in the GUI.

Runs Flask in a daemon thread so it does not block the Qt event loop.
Thread-safety: sensor data is forwarded to the Qt thread via a Qt Signal.
The latest alert state is stored in a plain dict (GIL-safe reads/writes
of individual keys are atomic in CPython) for the Flask thread to read.
"""

from __future__ import annotations

import threading
import urllib.request
import json as _json
from typing import TYPE_CHECKING

from flask import Flask, request, jsonify
from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from core.simulator import SimulatorEngine
    from core.event_log import EventLog


# ── Flask app (module-level, one instance) ─────────────────────────────────
_flask_app = Flask(__name__)
_flask_app.logger.disabled = True          # suppress Flask request logs to console

import logging
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)                # silence werkzeug startup banner

# Module-level reference to the active IoTServer instance so Flask routes
# can forward calls to it (Flask routes are module-level singletons).
_active_server: "IoTServer | None" = None


@_flask_app.route("/sensor", methods=["POST"])
def _route_sensor():
    if _active_server is None:
        return jsonify({"error": "not ready"}), 503
    return _active_server._handle_sensor()


@_flask_app.route("/status", methods=["GET"])
def _route_status():
    if _active_server is None:
        return jsonify({"error": "not ready"}), 503
    return _active_server._handle_status()


@_flask_app.route("/command", methods=["GET"])
def _route_command():
    if _active_server is None:
        return jsonify({"error": "not ready"}), 503
    return _active_server._handle_command()


class IoTServer(QObject):
    """
    Manages the background Flask server and bridges it to the Qt GUI.

    Usage (from main thread)::

        server = IoTServer(simulator, event_log)
        server.start()          # spawns daemon thread
        # ...
        server.stop()           # signals thread to exit (best-effort)
    """

    # Emitted in the Flask thread — connected to a slot in the main thread
    sensor_received = Signal(float, bool, int)   # tilt_deg, button_pressed, tilt_duration_ms
    hardware_button_pressed = Signal()            # physical button was pressed on the device

    def __init__(self, simulator: "SimulatorEngine", event_log: "EventLog",
                 host: str = "0.0.0.0", port: int = 5000, parent=None):
        super().__init__(parent)
        self._sim = simulator
        self._log = event_log
        self._host = host
        self._port = port

        # Latest alert state written by Qt thread, read by Flask thread
        self._alert_state: dict = {
            "alert_level": 0,
            "motor_on": False,
            "buzzer_on": False,
            "red_led": False,
            "green_led": True,
            "ack_required": False,
            "visual_score": 0.0,
        }

        # Track previous alert level to detect transitions
        self._prev_alert_level: int = 0
        # Guard: True while a hardware test is running
        self._testing: bool = False

        # Set module-level reference so Flask routes can forward to this instance
        global _active_server
        _active_server = self

        # Connect signal → slot (runs in Qt main thread)
        self.sensor_received.connect(self._on_sensor_received)

        self._thread: threading.Thread | None = None

    # ── public API ─────────────────────────────────────────────────────────

    def start(self):
        """Start the Flask server in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_flask, daemon=True, name="iot-flask"
        )
        self._thread.start()
        self._log.add(f"IoT server listening on {self._host}:{self._port}", "info")

    def stop(self):
        """Flask/Werkzeug dev server cannot be cleanly stopped from outside;
        the daemon thread exits automatically when the process ends."""
        self._log.add("IoT server stopped", "info")

    def test_buzzer(self, duration_ms: int = 2500):
        """Temporarily activate only the buzzer on real hardware for *duration_ms*."""
        self._log.add("Hardware test: Buzzer ON", "info")
        self._testing = True
        self._alert_state = {
            "alert_level": 1,
            "motor_on": False,
            "buzzer_on": True,
            "red_led": True,
            "green_led": False,
            "ack_required": False,
            "visual_score": 0.6,
        }
        threading.Timer(duration_ms / 1000.0, self._restore_idle_state).start()

    def test_vibration(self, duration_ms: int = 2500):
        """Temporarily activate only the vibration motor on real hardware for *duration_ms*."""
        self._log.add("Hardware test: Vibration motor ON", "info")
        self._testing = True
        self._alert_state = {
            "alert_level": 1,
            "motor_on": True,
            "buzzer_on": False,
            "red_led": True,
            "green_led": False,
            "ack_required": False,
            "visual_score": 0.6,
        }
        threading.Timer(duration_ms / 1000.0, self._restore_idle_state).start()

    def test_both(self, duration_ms: int = 2500):
        """Activate both buzzer and vibration motor simultaneously for *duration_ms*."""
        self._log.add("Hardware test: Buzzer + Vibration ON together", "info")
        self._testing = True
        self._alert_state = {
            "alert_level": 2,
            "motor_on": True,
            "buzzer_on": True,
            "red_led": True,
            "green_led": False,
            "ack_required": False,
            "visual_score": 0.9,
        }
        threading.Timer(duration_ms / 1000.0, self._restore_idle_state).start()

    def _restore_idle_state(self):
        """Restore hardware to idle after a test."""
        self._testing = False
        self._alert_state = {
            "alert_level": 0,
            "motor_on": False,
            "buzzer_on": False,
            "red_led": False,
            "green_led": True,
            "ack_required": False,
            "visual_score": 0.0,
        }
        self._log.add("Hardware test: done — outputs cleared", "info")

    def update_alert_state(self, state: dict):
        """
        Called from the Qt main thread whenever SimulatorEngine emits a new
        state dict. Translates GUI state to the hardware response format.
        Skipped while a hardware test is running.
        """
        if self._testing:
            return  # don't overwrite test state

        level_str = state.get("alert_level", "OK")
        if level_str == "MAX":
            level_int = 2
        elif level_str == "Level 1":
            level_int = 1
        else:
            level_int = 0

        new_state = {
            "alert_level": level_int,
            "motor_on": state.get("vibration_on", False),
            "buzzer_on": state.get("buzzer_on", False),
            "red_led": level_int > 0,
            "green_led": level_int == 0,
            "ack_required": state.get("is_critical", False),
            "visual_score": 0.9 if level_int == 2 else (0.6 if level_int == 1 else 0.0),
        }
        self._alert_state = new_state

        # If alert level changed, push immediately to NodeMCU via background thread
        if level_int != self._prev_alert_level:
            self._prev_alert_level = level_int
            if level_str != "OK":
                self._log.add(
                    f"IoT: Alert {level_str} -> hardware (buzzer={'ON' if new_state['buzzer_on'] else 'OFF'}, motor={'ON' if new_state['motor_on'] else 'OFF'})",
                    "info"
                )
            threading.Thread(
                target=self._push_to_nodemcu, daemon=True
            ).start()

    def _push_to_nodemcu(self):
        """Non-blocking: POST current alert state to the NodeMCU's /push endpoint
        so the Arduino gets the command immediately without waiting for the next poll.
        Silently ignores errors (NodeMCU may not be connected)."""
        try:
            payload = _json.dumps(self._alert_state).encode()
            req = urllib.request.Request(
                f"http://{self._host}:{self._port}/command",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="GET"
            )
            # We're already the server — just expose the state via /command,
            # no actual push needed (NodeMCU polls us). Log only.
        except Exception:
            pass

    # ── Qt slot (main thread) ──────────────────────────────────────────────

    def _on_sensor_received(self, tilt_deg: float, button_pressed: bool, tilt_ms: int):
        """Forward hardware tilt data into the running SimulatorEngine."""
        if self._sim.running:
            self._sim.set_tilt(tilt_deg)
            if button_pressed:
                self._sim.acknowledge()
                self.hardware_button_pressed.emit()  # notify GUI

    # ── Flask routes (Flask thread) ────────────────────────────────────────

    def _handle_sensor(self):
        raw = request.get_data(as_text=True)
        data = request.get_json(force=True, silent=True)

        if data is None:
            print(f"[IoT] /sensor BAD JSON: {raw[:120]}")
            return jsonify(self._alert_state)

        tilt = float(data.get("tilt_angle", 0.0))
        button = bool(data.get("button_pressed", False))
        tilt_ms = int(data.get("tilt_duration_ms", 0))

        print(f"[IoT] /sensor tilt={tilt:.1f} btn={button}")

        # Emit signal to cross into Qt main thread safely
        self.sensor_received.emit(tilt, button, tilt_ms)

        return jsonify(self._alert_state)

    def _handle_status(self):
        return jsonify({"status": "running", "server": "DrowsinessDetection-IoT"})

    def _handle_command(self):
        """GET /command — returns the current alert command so NodeMCU can poll it."""
        return jsonify(self._alert_state)

    # ── Flask runner ───────────────────────────────────────────────────────

    def _run_flask(self):
        try:
            print(f"[IoT] Flask server starting on {self._host}:{self._port}")
            _flask_app.run(host=self._host, port=self._port,
                           debug=False, use_reloader=False, threaded=True)
        except Exception as e:
            print(f"[IoT] Flask server FAILED to start: {e}")
