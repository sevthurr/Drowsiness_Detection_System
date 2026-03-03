"""Left panel — simulator controls, scenario buttons, manual inputs."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.cards import Card


class LeftPanel(QWidget):
    """Connection & Simulator panel (left column)."""

    start_requested = Signal()
    stop_requested = Signal()
    tilt_changed = Signal(float)
    force_eyes_closed_changed = Signal(bool)
    manual_yawns_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    # ── build ───────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(14)

        # Section title
        title = QLabel("Simulator")
        title.setStyleSheet("font-size:20px; font-weight:bold;")
        root.addWidget(title)

        # Start / Stop (standalone button, no card)
        self._btn_toggle = QPushButton("Start Simulation")
        self._btn_toggle.setFixedHeight(48)
        self._btn_toggle.setStyleSheet("font-size:15px; font-weight:bold;")
        self._btn_toggle.clicked.connect(self._on_toggle_simulation)
        self._is_running = False
        root.addWidget(self._btn_toggle)

        # Scenarios
        sc_card = Card()
        sl = QVBoxLayout(sc_card)
        sl.setContentsMargins(18, 14, 18, 14)
        sl.setSpacing(8)
        sc_lbl = QLabel("Scenarios")
        sc_lbl.setStyleSheet("font-size:14px; font-weight:600;")
        sl.addWidget(sc_lbl)

        scenarios = [
            ("Normal Driving", "normal"),
            ("Tilt  Level 1", "tilt_l1"),
            ("Eyes Closed  Level 2", "eyes_l2"),
            ("Yawn  Level 1", "yawn_l1"),
            ("No Acknowledge  MAX", "no_ack_max"),
        ]
        for text, key in scenarios:
            btn = QPushButton(text)
            btn.setObjectName("scenario")
            btn.clicked.connect(lambda _=False, k=key: self._apply_scenario(k))
            sl.addWidget(btn)

        root.addWidget(sc_card)

        # Manual controls
        man_card = Card()
        ml2 = QVBoxLayout(man_card)
        ml2.setContentsMargins(18, 14, 18, 14)
        ml2.setSpacing(10)
        mc_lbl = QLabel("Manual Controls")
        mc_lbl.setStyleSheet("font-size:14px; font-weight:600;")
        ml2.addWidget(mc_lbl)

        # Tilt slider
        ml2.addWidget(QLabel("Tilt angle (0-60°)"))
        tilt_row = QHBoxLayout()
        self._tilt_slider = QSlider(Qt.Orientation.Horizontal)
        self._tilt_slider.setRange(0, 60)
        self._tilt_slider.setValue(0)
        self._tilt_val = QLabel("0°")
        self._tilt_val.setFixedWidth(36)
        self._tilt_slider.valueChanged.connect(self._on_tilt)
        tilt_row.addWidget(self._tilt_slider)
        tilt_row.addWidget(self._tilt_val)
        ml2.addLayout(tilt_row)

        # Force eyes closed
        self._force_eyes = QCheckBox("Force eyes closed")
        self._force_eyes.toggled.connect(self.force_eyes_closed_changed)
        ml2.addWidget(self._force_eyes)

        # Yawns slider
        ml2.addWidget(QLabel("Yawns / 10 min (0-6)"))
        yawn_row = QHBoxLayout()
        self._yawn_slider = QSlider(Qt.Orientation.Horizontal)
        self._yawn_slider.setRange(0, 6)
        self._yawn_slider.setValue(0)
        self._yawn_val = QLabel("0")
        self._yawn_val.setFixedWidth(24)
        self._yawn_slider.valueChanged.connect(self._on_yawns)
        yawn_row.addWidget(self._yawn_slider)
        yawn_row.addWidget(self._yawn_val)
        ml2.addLayout(yawn_row)

        root.addWidget(man_card)

        root.addStretch()

    # ── handlers ────────────────────────────────────────────────────────────
    def _on_toggle_simulation(self):
        if self._is_running:
            self.stop_requested.emit()
            self._btn_toggle.setText("Start Simulation")
            self._btn_toggle.setObjectName("")
            self._is_running = False
        else:
            self.start_requested.emit()
            self._btn_toggle.setText("Stop Simulation")
            self._btn_toggle.setObjectName("danger")
            self._is_running = True
        # Force style refresh
        self._btn_toggle.style().unpolish(self._btn_toggle)
        self._btn_toggle.style().polish(self._btn_toggle)
    def _on_tilt(self, val: int):
        self._tilt_val.setText(f"{val}°")
        self.tilt_changed.emit(float(val))

    def _on_yawns(self, val: int):
        self._yawn_val.setText(str(val))
        self.manual_yawns_changed.emit(float(val))

    def _apply_scenario(self, key: str):
        # Auto-start simulation
        self.start_requested.emit()

        if key == "normal":
            self._tilt_slider.setValue(0)
            self._force_eyes.setChecked(False)
            self._yawn_slider.setValue(0)
        elif key == "tilt_l1":
            self._tilt_slider.setValue(45)
            self._force_eyes.setChecked(False)
            self._yawn_slider.setValue(0)
        elif key == "eyes_l2":
            self._tilt_slider.setValue(0)
            self._force_eyes.setChecked(True)
            self._yawn_slider.setValue(0)
        elif key == "yawn_l1":
            self._tilt_slider.setValue(0)
            self._force_eyes.setChecked(False)
            self._yawn_slider.setValue(4)
        elif key == "no_ack_max":
            self._tilt_slider.setValue(45)
            self._force_eyes.setChecked(False)
            self._yawn_slider.setValue(0)
