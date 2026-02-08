"""Dark / Light theme colour palettes and QSS stylesheet builder."""

DARK = {
    "bg": "#0d1117",
    "card": "#161b22",
    "border": "#30363d",
    "accent": "#00bcd4",
    "accent_hover": "#26c6da",
    "text": "#e6edf3",
    "text2": "#8b949e",
    "ok": "#3fb950",
    "warn": "#d29922",
    "danger": "#f85149",
    "input": "#0d1117",
    "scroll_bg": "#161b22",
    "scroll_handle": "#30363d",
    "nav_bg": "#090c10",
}

LIGHT = {
    "bg": "#f0f2f5",
    "card": "#ffffff",
    "border": "#d0d7de",
    "accent": "#0097a7",
    "accent_hover": "#00838f",
    "text": "#1f2328",
    "text2": "#656d76",
    "ok": "#1a7f37",
    "warn": "#9a6700",
    "danger": "#cf222e",
    "input": "#f6f8fa",
    "scroll_bg": "#ffffff",
    "scroll_handle": "#d0d7de",
    "nav_bg": "#e4e7ec",
}


def build_stylesheet(c: dict) -> str:
    """Return full application QSS parameterised by colour dict *c*."""
    return f"""
    /* ── global ────────────────────────────────────────── */
    QMainWindow, QWidget#centralWidget {{
        background-color: {c['bg']};
    }}
    QLabel {{
        color: {c['text']};
        background: transparent;
    }}
    QLabel[role="secondary"] {{
        color: {c['text2']};
    }}

    /* ── cards ─────────────────────────────────────────── */
    QFrame#card {{
        background-color: {c['card']};
        border: 1px solid {c['border']};
        border-radius: 14px;
    }}

    /* ── buttons ───────────────────────────────────────── */
    QPushButton {{
        background-color: {c['accent']};
        color: #ffffff;
        border: none;
        border-radius: 8px;
        padding: 8px 14px;
        font-weight: 600;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background-color: {c['accent_hover']};
    }}
    QPushButton:pressed {{
        background-color: {c['accent']};
    }}
    QPushButton:disabled {{
        background-color: {c['border']};
        color: {c['text2']};
    }}
    QPushButton#danger {{
        background-color: {c['danger']};
    }}
    QPushButton#danger:hover {{
        background-color: #ff6b63;
    }}
    QPushButton#ack {{
        background-color: {c['ok']};
        font-size: 15px;
        padding: 10px;
    }}
    QPushButton#ack:hover {{
        background-color: #4cd964;
    }}
    QPushButton#scenario {{
        background-color: {c['card']};
        color: {c['text']};
        border: 1px solid {c['border']};
        text-align: left;
        padding: 7px 12px;
    }}
    QPushButton#scenario:hover {{
        border-color: {c['accent']};
        color: {c['accent']};
    }}

    /* ── inputs ────────────────────────────────────────── */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {c['input']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 13px;
        min-height: 18px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border-color: {c['accent']};
    }}
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        background-color: {c['card']};
        color: {c['text2']};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 22px;
        border: none;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['card']};
        color: {c['text']};
        border: 1px solid {c['border']};
        selection-background-color: {c['accent']};
        selection-color: #ffffff;
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 18px;
        border: none;
        background: transparent;
    }}

    /* ── sliders ───────────────────────────────────────── */
    QSlider::groove:horizontal {{
        height: 6px;
        background: {c['border']};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {c['accent']};
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}
    QSlider::sub-page:horizontal {{
        background: {c['accent']};
        border-radius: 3px;
    }}

    /* ── checkboxes ────────────────────────────────────── */
    QCheckBox {{
        color: {c['text']};
        spacing: 8px;
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 2px solid {c['border']};
        background: {c['input']};
    }}
    QCheckBox::indicator:checked {{
        background: {c['accent']};
        border-color: {c['accent']};
    }}

    /* ── scroll areas ──────────────────────────────────── */
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: {c['scroll_bg']};
        width: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['scroll_handle']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        height: 0;
    }}

    /* ── list widget (event log) ───────────────────────── */
    QListWidget {{
        background-color: {c['card']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        color: {c['text']};
        font-size: 12px;
        padding: 4px;
        outline: 0;
    }}
    QListWidget::item {{
        padding: 3px 8px;
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background-color: {c['accent']};
        color: #ffffff;
    }}

    /* ── nav sidebar ───────────────────────────────────── */
    QWidget#navSidebar {{
        background-color: {c['nav_bg']};
    }}
    QPushButton#navBtn {{
        background: transparent;
        color: {c['text2']};
        border: none;
        border-radius: 10px;
        padding: 10px 4px;
        font-size: 18px;
        font-weight: 600;
        text-align: center;
    }}
    QPushButton#navBtn:checked {{
        background-color: {c['accent']};
        color: #ffffff;
    }}
    QPushButton#navBtn:hover:!checked {{
        background-color: {c['border']};
    }}

    /* ── group box ─────────────────────────────────────── */
    QGroupBox {{
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        margin-top: 14px;
        padding: 18px 10px 10px 10px;
        font-weight: 600;
        font-size: 13px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
    }}
    """
