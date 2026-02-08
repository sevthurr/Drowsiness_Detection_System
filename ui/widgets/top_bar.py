"""Top bar: title, alert level text, theme toggle button."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class TopBar(QWidget):
    """Horizontal top bar for the dashboard window."""

    theme_toggled = Signal(bool)  # True=dark

    def __init__(self, dark: bool = True, parent=None):
        super().__init__(parent)
        self._dark = dark
        self.setFixedHeight(48)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 18, 0)

        # Title
        title = QLabel("Driver Drowsiness Detection System")
        title.setStyleSheet("font-size:15px; font-weight:bold;")
        lay.addWidget(title)
        lay.addStretch()

        # Alert level text (instead of badge)
        lay.addWidget(QLabel("Alert Level:"))
        self._alert_lbl = QLabel("OK")
        self._alert_lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#3fb950;")
        lay.addWidget(self._alert_lbl)

        lay.addSpacing(20)

        # Theme toggle button (shows opposite theme)
        self._theme_btn = QPushButton("Light" if dark else "Dark")
        self._theme_btn.setFixedSize(80, 32)
        self._theme_btn.clicked.connect(self._on_toggle)
        lay.addWidget(self._theme_btn)

    # ── slots ───────────────────────────────────────────────────────
    def update_state(self, state: dict):
        level = state.get("alert_level", "OK")
        colors = {
            "OK": "#3fb950",
            "Level 1": "#d29922",
            "Level 2": "#f85149",
            "MAX": "#ff2020",
        }
        self._alert_lbl.setText(level)
        self._alert_lbl.setStyleSheet(
            f"font-size:14px; font-weight:bold; color:{colors.get(level, '#3fb950')};"
        )

    # ── private ─────────────────────────────────────────────────────
    def _on_toggle(self):
        self._dark = not self._dark
        # Update button to show opposite theme
        self._theme_btn.setText("Light" if self._dark else "Dark")
        self.theme_toggled.emit(self._dark)
