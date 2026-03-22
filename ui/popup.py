from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.router import route

# ── palette ─────────────────────────────────────────────────────────────────
_BG = "#1E1E2E"
_SURFACE = "#313244"
_BORDER = "#45475A"
_TEXT = "#CDD6F4"
_MUTED = "#6C7086"
_ACCENT = "#7C3AED"
_GREEN = "#1E3A2F"
_GREEN_TEXT = "#A6E3A1"
_BLUE = "#1E2D40"
_BLUE_TEXT = "#89B4FA"
_RED_BG = "#2A1A1A"
_RED_TEXT = "#F38BA8"
_USER_TEXT = "#CDD6F4"


# ── multiline input ──────────────────────────────────────────────────────────
class _ChatInput(QTextEdit):
    """QTextEdit that submits on Enter and inserts newline on Ctrl+Enter/Shift+Enter."""

    submitted = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptRichText(False)
        self.setFixedHeight(38)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
                self.insertPlainText("\n")
                self._auto_grow()
                return
            else:
                self.submitted.emit()
                return
        super().keyPressEvent(event)
        self._auto_grow()

    def _auto_grow(self) -> None:
        doc_height = int(self.document().size().height()) + 16
        self.setFixedHeight(max(38, min(doc_height, 120)))

    def clear(self) -> None:
        super().clear()
        self.setFixedHeight(38)


# ── background worker ────────────────────────────────────────────────────────
class _Worker(QObject):
    finished: Signal = Signal(str, str)  # (kind, response)

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def run(self) -> None:
        kind, response = route(self._text)
        self.finished.emit(kind, response)


# ── ingest worker ────────────────────────────────────────────────────────────
class _IngestWorker(QObject):
    finished: Signal = Signal(str, str)  # (kind, response)

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self._path = file_path

    def run(self) -> None:
        try:
            from core.rag import ingest_file
            msg = ingest_file(self._path)
            self.finished.emit("memory", msg)
        except Exception as e:
            self.finished.emit("error", str(e))


# ── popup window ─────────────────────────────────────────────────────────────
class SagePopup(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(420)

        self._thread: QThread | None = None
        self._worker: _Worker | None = None

        self._build_ui()

    # ── layout ───────────────────────────────────────────────────────────────
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
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # title row
        title_row = QHBoxLayout()
        title = QLabel("Sage")
        title.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_TEXT};")
        title_row.addWidget(title)
        title_row.addStretch()
        close_btn = QPushButton("\u00d7")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                color: {_MUTED}; background: transparent; border: none; font-size: 16px;
            }}
            QPushButton:hover {{ color: {_TEXT}; }}
        """)
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        hint = QLabel("Type a note to save it. End with ? to ask from memory or documents.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        layout.addWidget(hint)

        # history
        self._history_widget = QWidget()
        self._history_layout = QVBoxLayout(self._history_widget)
        self._history_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._history_layout.setSpacing(6)
        self._history_layout.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(220)
        self._scroll.setWidget(self._history_widget)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                width: 4px; background: {_SURFACE}; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORDER}; border-radius: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        layout.addWidget(self._scroll)

        # separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_BORDER};")
        layout.addWidget(sep)

        # input row
        row = QHBoxLayout()

        attach_btn = QPushButton("+")
        attach_btn.setFixedSize(38, 38)
        attach_btn.setToolTip("Upload document (PDF, CSV, Excel)")
        attach_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_SURFACE}; color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 8px; font-size: 18px; font-weight: bold;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
            QPushButton:pressed {{ background: {_ACCENT}; color: white; }}
        """)
        attach_btn.clicked.connect(self._attach_file)
        self._attach_btn = attach_btn
        row.addWidget(attach_btn)

        self._input = _ChatInput()
        self._input.setPlaceholderText("Type a note or end with ? to ask a question")
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: {_SURFACE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QTextEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        self._input.submitted.connect(self._submit)
        row.addWidget(self._input)

        send_btn = QPushButton("\u2192")
        send_btn.setFixedSize(38, 38)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white;
                border-radius: 8px; font-size: 17px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #6D28D9; }}
            QPushButton:pressed {{ background: #5B21B6; }}
            QPushButton:disabled {{ background: {_SURFACE}; color: {_MUTED}; }}
        """)
        send_btn.clicked.connect(self._submit)
        self._send_btn = send_btn
        row.addWidget(send_btn)
        layout.addLayout(row)

        # status
        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        layout.addWidget(self._status)

    # ── submit ────────────────────────────────────────────────────────────────
    def _submit(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return

        self._input.clear()
        self._set_busy(True)
        self._add_bubble(text, role="user")

        self._thread = QThread()
        self._worker = _Worker(text)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_result)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(lambda: setattr(self, '_thread', None))
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_result(self, kind: str, response: str) -> None:
        self._add_bubble(response, role=kind)
        self._set_busy(False)

    # ── attach file ──────────────────────────────────────────────────────────
    def _attach_file(self) -> None:
        from pathlib import Path

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Upload document",
            "",
            "Documents (*.pdf *.csv *.xls *.xlsx);;All Files (*)",
        )
        if not path:
            return

        self._set_busy(True)
        self._add_bubble(f"Uploading: {Path(path).name}", role="user")

        self._thread = QThread()
        self._worker = _IngestWorker(path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_result)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(lambda: setattr(self, '_thread', None))
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _set_busy(self, busy: bool) -> None:
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy)
        self._attach_btn.setEnabled(not busy)
        self._status.setText("Processing\u2026" if busy else "")
        if not busy:
            self._input.setFocus()

    def _add_bubble(self, text: str, role: str) -> None:
        if role == "user":
            bg, fg, align = _SURFACE, _USER_TEXT, Qt.AlignmentFlag.AlignRight
        elif role == "memory":
            bg, fg, align = _GREEN, _GREEN_TEXT, Qt.AlignmentFlag.AlignLeft
        elif role == "error":
            bg, fg, align = _RED_BG, _RED_TEXT, Qt.AlignmentFlag.AlignLeft
        else:  # answer
            bg, fg, align = _BLUE, _BLUE_TEXT, Qt.AlignmentFlag.AlignLeft

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(360)
        bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        bubble.setCursor(Qt.CursorShape.IBeamCursor)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        bubble.setStyleSheet(f"""
            background: {bg};
            color: {fg};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12px;
            selection-background-color: {_ACCENT};
        """)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if align == Qt.AlignmentFlag.AlignRight:
            row.addStretch()
        row.addWidget(bubble)
        if align == Qt.AlignmentFlag.AlignLeft:
            row.addStretch()

        self._history_layout.addLayout(row)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── show / hide ──────────────────────────────────────────────────────────
    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self._position()
            self.show()
            self.raise_()
            self.activateWindow()
            self._input.setFocus()

    def _position(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        x = screen.right() - self.width() - 20
        y = screen.bottom() - self.height() - 60
        self.move(x, y)

    # ── keyboard ─────────────────────────────────────────────────────────────
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
