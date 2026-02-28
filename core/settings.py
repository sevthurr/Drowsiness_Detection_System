"""Persistent settings backed by config.json."""

import json
import os

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_DIR, "config.json")

DEFAULTS = {
    "theme": "dark",
    "device_name": "Drowsiness Detector",
    "hotspot_ssid": "DrowsiGuard",
    "buzzer_freq_hz": 2000,
    "vibration_freq_l1": 2.0,
    "vibration_freq_l2": 5.0,
    "alarm_track": 1,
    "alarm_volume": 15,
    "thresholds_override": False,
    "tilt_threshold_deg": 30.0,
    "tilt_duration_s": 3.0,
    "eyes_closed_threshold_s": 2.0,
    "eyes_critical_s": 4.0,
    "yawns_per_min_threshold": 2.0,
    "acknowledge_timeout_s": 10.0,
}


class Settings:
    """Simple key-value store persisted to *config.json*."""

    def __init__(self):
        self._data: dict = dict(DEFAULTS)
        self.load()

    # -- access -------------------------------------------------------
    def get(self, key: str, default=None):
        val = self._data.get(key)
        if val is not None:
            return val
        if default is not None:
            return default
        return DEFAULTS.get(key)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def update(self, mapping: dict):
        self._data.update(mapping)
        self.save()

    def all(self) -> dict:
        return dict(self._data)

    # -- persistence --------------------------------------------------
    def load(self):
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for k in DEFAULTS:
                if k in data:
                    self._data[k] = data[k]
        except Exception:
            pass

    def save(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except Exception:
            pass
