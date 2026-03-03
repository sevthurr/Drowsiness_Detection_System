"""Right panel — device identity and alert customisation."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
        card_a.setMinimumHeight(220)
        la = QVBoxLayout(card_a)
        la.setContentsMargins(24, 20, 24, 20)
        la.setSpacing(12)
        la.addWidget(self._section_lbl("Device Identity"))

        lbl_name = QLabel("Device Name")
        lbl_name.setStyleSheet("font-size:13px;")
        la.addWidget(lbl_name)
        self._inp_name = QLineEdit()
        self._inp_name.setPlaceholderText("e.g. My Detector")
        self._inp_name.setMinimumHeight(36)
        self._inp_name.setStyleSheet("font-size:13px; padding:6px;")
        self._inp_name.editingFinished.connect(
            lambda: self._save("device_name", self._inp_name.text())
        )
        la.addWidget(self._inp_name)

        lbl_ssid = QLabel("Hotspot SSID (1-32 chars)")
        lbl_ssid.setStyleSheet("font-size:13px;")
        la.addWidget(lbl_ssid)
        self._inp_ssid = QLineEdit()
        self._inp_ssid.setMaxLength(32)
        self._inp_ssid.setPlaceholderText("e.g. DrowsiGuard")
        self._inp_ssid.setMinimumHeight(36)
        self._inp_ssid.setStyleSheet("font-size:13px; padding:6px;")
        self._inp_ssid.editingFinished.connect(self._on_ssid)
        la.addWidget(self._inp_ssid)
        self._ssid_err = QLabel("")
        self._ssid_err.setStyleSheet("color:#f85149; font-size:12px;")
        la.addWidget(self._ssid_err)

        root.addWidget(card_a)

        # ── B: Alert Customisation ──────────────────────────────────
        card_b = Card()
        card_b.setMinimumHeight(240)
        lb = QVBoxLayout(card_b)
        lb.setContentsMargins(24, 20, 24, 20)
        lb.setSpacing(12)
        lb.addWidget(self._section_lbl("Alert Customisation"))

        lbl_buzz = QLabel("Buzzer Frequency (Hz)")
        lbl_buzz.setStyleSheet("font-size:13px;")
        lb.addWidget(lbl_buzz)
        self._spn_buzz = QSpinBox()
        self._spn_buzz.setRange(100, 4000)
        self._spn_buzz.setSingleStep(100)
        self._spn_buzz.setMinimumHeight(36)
        self._spn_buzz.setStyleSheet("font-size:13px;")
        self._spn_buzz.valueChanged.connect(
            lambda v: self._save("buzzer_freq_hz", v)
        )
        lb.addWidget(self._spn_buzz)

        lbl_vol = QLabel("Alarm Volume")
        lbl_vol.setStyleSheet("font-size:13px;")
        lb.addWidget(lbl_vol)
        vol_row = QHBoxLayout()
        self._sld_vol = QSlider(Qt.Orientation.Horizontal)
        self._sld_vol.setRange(0, 30)
        self._sld_vol.setMinimumHeight(24)
        self._vol_lbl = QLabel("15")
        self._vol_lbl.setFixedWidth(32)
        self._vol_lbl.setStyleSheet("font-size:13px;")
        self._sld_vol.valueChanged.connect(self._on_vol)
        vol_row.addWidget(self._sld_vol)
        vol_row.addWidget(self._vol_lbl)
        lb.addLayout(vol_row)

        # Test buttons
        trow = QHBoxLayout()
        trow.setSpacing(10)
        btn_tbuzz = QPushButton("Test Buzz")
        btn_tbuzz.setMinimumHeight(38)
        btn_tbuzz.setStyleSheet("font-size:13px;")
        btn_tvib = QPushButton("Test Vibration")
        btn_tvib.setMinimumHeight(38)
        btn_tvib.setStyleSheet("font-size:13px;")
        btn_talarm = QPushButton("Test Alarm")
        btn_talarm.setMinimumHeight(38)
        btn_talarm.setStyleSheet("font-size:13px;")
        btn_tbuzz.clicked.connect(self.test_buzzer)
        btn_tvib.clicked.connect(self.test_vibration)
        btn_talarm.clicked.connect(self.test_alarm)
        trow.addWidget(btn_tbuzz)
        trow.addWidget(btn_tvib)
        trow.addWidget(btn_talarm)
        lb.addLayout(trow)

        root.addWidget(card_b)
        root.addStretch()

    # ── load persisted values ───────────────────────────────────────
    def _load(self):
        s = self._settings
        self._inp_name.setText(str(s.get("device_name", "")))
        self._inp_ssid.setText(str(s.get("hotspot_ssid", "")))
        self._spn_buzz.setValue(int(s.get("buzzer_freq_hz", 2000)))

        self._sld_vol.setValue(int(s.get("alarm_volume", 15)))
        self._vol_lbl.setText(str(int(s.get("alarm_volume", 15))))

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

    # ── helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _section_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size:16px; font-weight:600;")
        return lbl
