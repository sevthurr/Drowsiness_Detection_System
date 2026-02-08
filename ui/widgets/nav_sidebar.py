"""Narrow left-side navigation sidebar."""

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget
import qtawesome as qta


class NavSidebar(QWidget):
    """Vertical nav bar with Font Awesome icon buttons."""

    page_changed = Signal(int)  # 0=Live, 1=Simulator, 2=Settings

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navSidebar")
        self.setFixedWidth(60)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 20, 6, 14)
        lay.setSpacing(8)

        # Font Awesome icons with tooltips
        icon_names = ["video", "play", "cog"]  # video, gamepad, settings (cog)
        tooltips = ["Live Monitoring", "Simulator", "Settings"]
        self._buttons = []
        
        for i, (icon_name, tip) in enumerate(zip(icon_names, tooltips)):
            btn = QPushButton()
            btn.setIcon(qta.icon(f"fa5s.{icon_name}", color="white"))
            btn.setIconSize(QSize(22, 22))
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
