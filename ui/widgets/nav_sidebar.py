"""Narrow left-side navigation sidebar."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget


class NavSidebar(QWidget):
    """Vertical nav bar with icon-based page-switch buttons."""

    page_changed = Signal(int)  # 0=Live, 1=Simulator, 2=Settings

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navSidebar")
        self.setFixedWidth(60)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 20, 6, 14)
        lay.setSpacing(8)

        # Icon-based navigation buttons (using Unicode symbols)
        icons = ["\u25a0", "\u2699", "\u2630"]  # Live (square), Settings (gear), Menu (hamburger)
        tooltips = ["Live Monitoring", "Simulator", "Settings"]
        self._buttons = []
        
        for i, (icon, tip) in enumerate(zip(icons, tooltips)):
            btn = QPushButton(icon)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(48)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, idx=i: self._on_click(idx))
            lay.addWidget(btn)
            self._buttons.append(btn)

        lay.addStretch()
        self._buttons[0].setChecked(True)

    def _on_click(self, idx):
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == idx)
        self.page_changed.emit(idx)
