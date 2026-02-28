"""Right panel — device identity, alert customisation, threshold settings."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.cards import Card


class RightPanel(QWidget):
    """Settings & customisation panel (right column)."""

    settings_changed = Signal(str, object)  # key, value
    test_buzzer = Signal()
    test_vibration = Signal()
    test_alarm = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._build()
        self._load()

    # ── build ───────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(14)

        title = QLabel("Settings")
        title.setStyleSheet("font-size:20px; font-weight:bold;")
        root.addWidget(title)

        # ── A: Device Identity ──────────────────────────────────────
        card_a = Card()
        la = QVBoxLayout(card_a)
        la.setContentsMargins(18, 14, 18, 14)
        la.setSpacing(8)
        la.addWidget(self._section_lbl("Device Identity"))

        la.addWidget(QLabel("Device Name"))
        self._inp_name = QLineEdit()
        self._inp_name.setPlaceholderText("e.g. My Detector")
        self._inp_name.editingFinished.connect(
            lambda: self._save("device_name", self._inp_name.text())
        )
        la.addWidget(self._inp_name)

        la.addWidget(QLabel("Hotspot SSID (1-32 chars)"))
        self._inp_ssid = QLineEdit()
        self._inp_ssid.setMaxLength(32)
        self._inp_ssid.setPlaceholderText("e.g. DrowsiGuard")
        self._inp_ssid.editingFinished.connect(self._on_ssid)
        la.addWidget(self._inp_ssid)
        self._ssid_err = QLabel("")
        self._ssid_err.setStyleSheet("color:#f85149; font-size:11px;")
        la.addWidget(self._ssid_err)

        root.addWidget(card_a)

        # ── B: Alert Customisation ──────────────────────────────────
        card_b = Card()
        lb = QVBoxLayout(card_b)
        lb.setContentsMargins(18, 14, 18, 14)
        lb.setSpacing(8)
        lb.addWidget(self._section_lbl("Alert Customisation"))

        lb.addWidget(QLabel("Buzzer Frequency (Hz)"))
        self._spn_buzz = QSpinBox()
        self._spn_buzz.setRange(100, 4000)
        self._spn_buzz.setSingleStep(100)
        self._spn_buzz.valueChanged.connect(
            lambda v: self._save("buzzer_freq_hz", v)
        )
        lb.addWidget(self._spn_buzz)

        lb.addWidget(QLabel("Alarm Volume"))
        vol_row = QHBoxLayout()
        self._sld_vol = QSlider(Qt.Orientation.Horizontal)
        self._sld_vol.setRange(0, 30)
        self._vol_lbl = QLabel("15")
        self._vol_lbl.setFixedWidth(28)
        self._sld_vol.valueChanged.connect(self._on_vol)
        vol_row.addWidget(self._sld_vol)
        vol_row.addWidget(self._vol_lbl)
        lb.addLayout(vol_row)

        # Test buttons
        trow = QHBoxLayout()
        btn_tbuzz = QPushButton("Test Buzz")
        btn_talarm = QPushButton("Test Alarm")
        btn_tbuzz.clicked.connect(self.test_buzzer)
        btn_talarm.clicked.connect(self.test_alarm)
        trow.addWidget(btn_tbuzz)
        trow.addWidget(btn_talarm)
        lb.addLayout(trow)

        root.addWidget(card_b)

        # ── C: Thresholds ───────────────────────────────────────────
        card_c = Card()
        lc = QVBoxLayout(card_c)
        lc.setContentsMargins(14, 10, 14, 10)
        lc.setSpacing(6)
        lc.addWidget(self._section_lbl("Thresholds"))

        self._chk_override = QCheckBox("Override Thresholds")
        self._chk_override.toggled.connect(self._on_override)
        lc.addWidget(self._chk_override)

        self._th_widgets: list[QDoubleSpinBox] = []

        def _add_th(label_text, key, lo, hi, step, decimals=1):
            lc.addWidget(QLabel(label_text))
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setSingleStep(step)
            sb.setDecimals(decimals)
            sb.setEnabled(False)
            sb.valueChanged.connect(lambda v, k=key: self._save(k, v))
            lc.addWidget(sb)
            self._th_widgets.append(sb)
            return sb

        self._th_tilt_deg = _add_th("Tilt threshold (°)", "tilt_threshold_deg", 5, 60, 5, 0)
        self._th_tilt_dur = _add_th("Tilt duration (s)", "tilt_duration_s", 1, 15, 0.5)
        self._th_eyes_s = _add_th("Eyes closed (s)", "eyes_closed_threshold_s", 0.5, 10, 0.5)
        self._th_eyes_crit = _add_th("Eyes critical (s)", "eyes_critical_s", 1, 15, 0.5)
        self._th_yawns = _add_th("Yawns/min threshold", "yawns_per_min_threshold", 1, 10, 1, 0)
        self._th_ack_t = _add_th("Ack timeout (s)", "acknowledge_timeout_s", 3, 30, 1, 0)

        root.addWidget(card_c)
        root.addStretch()

    # ── load persisted values ───────────────────────────────────────
    def _load(self):
        s = self._settings
        self._inp_name.setText(str(s.get("device_name", "")))
        self._inp_ssid.setText(str(s.get("hotspot_ssid", "")))
        self._spn_buzz.setValue(int(s.get("buzzer_freq_hz", 2000)))

        self._sld_vol.setValue(int(s.get("alarm_volume", 15)))
        self._vol_lbl.setText(str(int(s.get("alarm_volume", 15))))

        self._chk_override.setChecked(bool(s.get("thresholds_override", False)))

        self._th_tilt_deg.setValue(float(s.get("tilt_threshold_deg", 30)))
        self._th_tilt_dur.setValue(float(s.get("tilt_duration_s", 3)))
        self._th_eyes_s.setValue(float(s.get("eyes_closed_threshold_s", 2)))
        self._th_eyes_crit.setValue(float(s.get("eyes_critical_s", 4)))
        self._th_yawns.setValue(float(s.get("yawns_per_min_threshold", 2)))
        self._th_ack_t.setValue(float(s.get("acknowledge_timeout_s", 10)))

    # ── handlers ────────────────────────────────────────────────────
    def _save(self, key: str, value):
        self._settings.set(key, value)
        self.settings_changed.emit(key, value)

    def _on_ssid(self):
        text = self._inp_ssid.text().strip()
        if 0 < len(text) <= 32:
            self._ssid_err.setText("")
            self._save("hotspot_ssid", text)
        else:
            self._ssid_err.setText("SSID must be 1-32 characters")

    def _on_vol(self, v: int):
        self._vol_lbl.setText(str(v))
        self._save("alarm_volume", v)

    def _on_override(self, checked: bool):
        self._save("thresholds_override", checked)
        for w in self._th_widgets:
            w.setEnabled(checked)

    # ── helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _section_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size:14px; font-weight:600;")
        return lbl
