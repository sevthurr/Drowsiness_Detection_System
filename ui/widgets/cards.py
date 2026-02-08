"""Reusable card widgets for the dashboard."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class Card(QFrame):
    """Dark-themed card container with rounded corners."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.StyledPanel)


class MetricCard(Card):
    """Card that displays a single labelled value."""

    def __init__(self, label: str, initial: str = "--", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)

        self._lbl = QLabel(label)
        self._lbl.setProperty("role", "secondary")
        self._lbl.setStyleSheet("font-size: 11px;")

        self._val = QLabel(initial)
        self._val.setStyleSheet("font-size: 22px; font-weight: bold;")
        self._val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        lay.addWidget(self._lbl)
        lay.addWidget(self._val)

    def set_value(self, text: str, color=None):
        style = "font-size: 22px; font-weight: bold;"
        if color:
            style += f" color: {color};"
        self._val.setStyleSheet(style)
        self._val.setText(text)
