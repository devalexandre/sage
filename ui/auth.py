"""
Login / Register dialog shown before the tray is created.
"""

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.auth_client import AuthClient, AuthError, NetworkError

_BG      = "#1E1E2E"
_SURFACE = "#313244"
_BORDER  = "#45475A"
_TEXT    = "#CDD6F4"
_MUTED   = "#6C7086"
_ACCENT  = "#7C3AED"
_GREEN   = "#A6E3A1"
_RED     = "#F38BA8"


# ── background worker ─────────────────────────────────────────────────────────

class _AuthWorker(QObject):
    finished = Signal(dict)
    failed   = Signal(str)

    def __init__(self, mode: str, email: str, password: str, client: AuthClient) -> None:
        super().__init__()
        self._mode   = mode
        self._email  = email
        self._pw     = password
        self._client = client

    def run(self) -> None:
        try:
            if self._mode == "login":
                result = self._client.login(self._email, self._pw)
            else:
                result = self._client.register(self._email, self._pw)
            self.finished.emit(result)
        except AuthError as e:
            self.failed.emit(e.message)
        except NetworkError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Unexpected error: {e}")


# ── auth dialog ───────────────────────────────────────────────────────────────

class SageAuthDialog(QWidget):
    login_success    = Signal(dict)   # emits API response dict
    register_success = Signal(dict)

    def __init__(self, api_url: str | None = None) -> None:
        super().__init__()
        self._client = AuthClient(api_url)
        self._mode   = "login"
        self._thread: QThread | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._build_ui()
        self._center()

    # ── build UI ──────────────────────────────────────────────────────────────
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
        layout.setSpacing(10)

        # Title
        title = QLabel("Sage")
        title.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_TEXT};")
        layout.addWidget(title)

        self._subtitle = QLabel("Sign in to continue")
        self._subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        layout.addWidget(self._subtitle)

        # Tab row
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self._login_tab = self._make_tab("Login", active=True)
        self._reg_tab   = self._make_tab("Register", active=False)
        self._login_tab.clicked.connect(lambda: self._switch("login"))
        self._reg_tab.clicked.connect(lambda: self._switch("register"))
        tab_row.addWidget(self._login_tab)
        tab_row.addWidget(self._reg_tab)
        layout.addLayout(tab_row)

        # Fields
        self._email_input = self._make_input("Email", False)
        self._pw_input    = self._make_input("Password", True)
        self._cpw_input   = self._make_input("Confirm Password", True)
        layout.addWidget(self._email_input)
        layout.addWidget(self._pw_input)
        layout.addWidget(self._cpw_input)
        self._cpw_input.hide()

        # Submit
        self._submit_btn = QPushButton("Sign in")
        self._submit_btn.setFixedHeight(38)
        self._submit_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white;
                border-radius: 8px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #6D28D9; }}
            QPushButton:disabled {{ background: {_SURFACE}; color: {_MUTED}; }}
        """)
        self._submit_btn.clicked.connect(self._submit)
        layout.addWidget(self._submit_btn)

        # Status
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {_RED}; font-size: 11px;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)

        # Enter key
        self._pw_input.returnPressed.connect(self._submit)
        self._cpw_input.returnPressed.connect(self._submit)

    @staticmethod
    def _make_tab(label: str, active: bool) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(32)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_SURFACE if not active else _ACCENT};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                font-size: 13px;
            }}
            QPushButton:checked {{ background: {_ACCENT}; border-color: {_ACCENT}; }}
            QPushButton:hover   {{ border-color: {_ACCENT}; }}
        """)
        return btn

    @staticmethod
    def _make_input(placeholder: str, password: bool) -> QLineEdit:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        if password:
            inp.setEchoMode(QLineEdit.EchoMode.Password)
        inp.setStyleSheet(f"""
            QLineEdit {{
                background: {_SURFACE}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        return inp

    # ── mode switch ───────────────────────────────────────────────────────────
    def _switch(self, mode: str) -> None:
        self._mode = mode
        is_reg = mode == "register"
        self._cpw_input.setVisible(is_reg)
        self._submit_btn.setText("Create account" if is_reg else "Sign in")
        self._subtitle.setText(
            "Create a free account" if is_reg else "Sign in to continue"
        )
        self._login_tab.setChecked(not is_reg)
        self._reg_tab.setChecked(is_reg)
        self._status.setText("")
        self.adjustSize()

    # ── submit ────────────────────────────────────────────────────────────────
    def _submit(self) -> None:
        if self._thread and self._thread.isRunning():
            return

        email = self._email_input.text().strip()
        pw    = self._pw_input.text()

        if not email or not pw:
            self._status.setText("Email and password are required.")
            return

        if self._mode == "register":
            cpw = self._cpw_input.text()
            if pw != cpw:
                self._status.setText("Passwords do not match.")
                return
            if len(pw) < 8:
                self._status.setText("Password must be at least 8 characters.")
                return

        self._set_busy(True)

        self._thread = QThread()
        self._worker = _AuthWorker(self._mode, email, pw, self._client)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_success)
        self._worker.failed.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(lambda: setattr(self, '_thread', None))
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_success(self, result: dict) -> None:
        self._set_busy(False)
        if self._mode == "login":
            self.login_success.emit(result)
        else:
            self.register_success.emit(result)

    def _on_error(self, msg: str) -> None:
        self._set_busy(False)
        self._status.setText(msg)

    def _set_busy(self, busy: bool) -> None:
        self._submit_btn.setEnabled(not busy)
        self._email_input.setEnabled(not busy)
        self._pw_input.setEnabled(not busy)
        self._cpw_input.setEnabled(not busy)
        self._submit_btn.setText(
            ("Creating…" if self._mode == "register" else "Signing in…")
            if busy
            else ("Create account" if self._mode == "register" else "Sign in")
        )
        self._status.setText("")

    def _center(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            pass  # Block — user must authenticate
        else:
            super().keyPressEvent(event)
