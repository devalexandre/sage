"""
One-time recovery phrase dialog shown on first run.
The user must copy the phrase and confirm before proceeding.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_BG      = "#1E1E2E"
_SURFACE = "#313244"
_BORDER  = "#45475A"
_TEXT    = "#CDD6F4"
_MUTED   = "#6C7086"
_ACCENT  = "#7C3AED"
_GREEN   = "#A6E3A1"
_YELLOW  = "#F9E2AF"
_WARN_BG = "#2A2417"


class SageRecoveryDialog(QWidget):
    confirmed = Signal()

    def __init__(self, recovery_phrase: str) -> None:
        super().__init__()
        self._phrase = recovery_phrase
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(480)
        self._build_ui()
        self._center()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"""
            QFrame#card {{
                background: {_BG};
                border: 1px solid {_BORDER};
                border-radius: 14px;
            }}
        """)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("Save Your Recovery Phrase")
        title.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_TEXT};")
        layout.addWidget(title)

        # Warning
        warn = QLabel(
            "⚠  If you lose this phrase and your device fails, "
            "your encrypted notes cannot be recovered."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"""
            color: {_YELLOW};
            background: {_WARN_BG};
            border: 1px solid {_YELLOW};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12px;
        """)
        layout.addWidget(warn)

        # Phrase box
        phrase_box = QTextEdit()
        phrase_box.setReadOnly(True)
        phrase_box.setPlainText(self._phrase)
        phrase_box.setFixedHeight(60)
        phrase_box.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        phrase_box.setStyleSheet(f"""
            QTextEdit {{
                background: {_SURFACE};
                color: {_GREEN};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 8px 12px;
            }}
        """)
        layout.addWidget(phrase_box)

        # Copy button
        copy_btn = QPushButton("Copy to clipboard")
        copy_btn.setFixedHeight(32)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_SURFACE}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 7px;
                font-size: 12px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        copy_btn.clicked.connect(self._copy)
        layout.addWidget(copy_btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_BORDER};")
        layout.addWidget(sep)

        # Checkbox
        self._check = QCheckBox("I have written down / saved my recovery phrase")
        self._check.setStyleSheet(f"""
            QCheckBox {{
                color: {_TEXT}; font-size: 13px; spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {_BORDER}; border-radius: 4px;
                background: {_SURFACE};
            }}
            QCheckBox::indicator:checked {{
                background: {_ACCENT}; border-color: {_ACCENT};
            }}
        """)
        self._check.toggled.connect(self._on_check)
        layout.addWidget(self._check)

        # Confirm button
        self._confirm_btn = QPushButton("Continue →")
        self._confirm_btn.setFixedHeight(38)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white;
                border-radius: 8px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #6D28D9; }}
            QPushButton:disabled {{
                background: {_SURFACE}; color: {_MUTED};
            }}
        """)
        self._confirm_btn.clicked.connect(self._confirm)
        layout.addWidget(self._confirm_btn)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._phrase)

    def _on_check(self, checked: bool) -> None:
        self._confirm_btn.setEnabled(checked)

    def _confirm(self) -> None:
        self.confirmed.emit()
        self.hide()

    def _center(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            pass  # Block Esc — user must confirm
        else:
            super().keyPressEvent(event)
