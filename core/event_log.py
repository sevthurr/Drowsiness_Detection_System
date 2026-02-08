"""Central event log with Qt signal notification."""

from datetime import datetime
from PySide6.QtCore import QObject, Signal


class EventLog(QObject):
    """Append-only event log that emits *entry_added* on each new entry."""

    entry_added = Signal(str, str, str)  # timestamp, message, level

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []

    def add(self, message: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.entries.append((ts, message, level))
        self.entry_added.emit(ts, message, level)

    def clear(self):
        self.entries.clear()
