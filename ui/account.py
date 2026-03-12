"""
Account & License dialog — accessible from the tray "Account" menu item.
Shows plan, memory usage, subscription check, and device deactivation.
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

from core import config as cfg
from core.auth_client import AuthClient, AuthError, NetworkError
from core.license import FREE_MEMORY_LIMIT, count_memories, get_device_id

_BG      = "#1E1E2E"
_SURFACE = "#313244"
_BORDER  = "#45475A"
_TEXT    = "#CDD6F4"
_MUTED   = "#6C7086"
_ACCENT  = "#7C3AED"
_GREEN   = "#A6E3A1"
_RED     = "#F38BA8"
_GOLD    = "#F9E2AF"


class _Worker(QObject):
    done  = Signal(dict)
    error = Signal(str)

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except (AuthError, NetworkError, Exception) as e:
            self.error.emit(str(e))


class SageAccount(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(360)
        self._thread: QThread | None = None
        self._build_ui()

    # ── layout ────────────────────────────────────────────────────────────────
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
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Account")
        title.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_TEXT};")
        title_row.addWidget(title)
        title_row.addStretch()
        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(f"""
            QPushButton {{ color: {_MUTED}; background: transparent; border: none; font-size: 16px; }}
            QPushButton:hover {{ color: {_TEXT}; }}
        """)
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        layout.addWidget(_sep())

        # User info
        self._email_lbl = QLabel("")
        self._email_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        layout.addWidget(self._email_lbl)

        # Plan badge + memory count row
        badge_row = QHBoxLayout()
        self._plan_badge = QLabel("PRO")
        badge_row.addWidget(self._plan_badge)
        badge_row.addStretch()
        self._mem_lbl = QLabel("")
        self._mem_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        badge_row.addWidget(self._mem_lbl)
        layout.addLayout(badge_row)

        layout.addWidget(_sep())

        # Subscription check
        self._check_frame = QFrame()
        clay = QVBoxLayout(self._check_frame)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(6)
        clay.addWidget(_section_lbl("Subscription"))
        self._order_input = QLineEdit()
        self._order_input.setPlaceholderText("Order ID (from Gumroad email)")
        self._order_input.setStyleSheet(_input_style())
        clay.addWidget(self._order_input)
        self._check_btn = QPushButton("Activate")
        self._check_btn.setFixedHeight(34)
        self._check_btn.setStyleSheet(_btn_style())
        self._check_btn.clicked.connect(self._check_subscriber)
        clay.addWidget(self._check_btn)
        self._check_status = QLabel("")
        self._check_status.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        clay.addWidget(self._check_status)
        layout.addWidget(self._check_frame)

        # Deactivate device
        self._deactivate_frame = QFrame()
        dlay = QVBoxLayout(self._deactivate_frame)
        dlay.setContentsMargins(0, 0, 0, 0)
        dlay.setSpacing(6)
        dlay.addWidget(_section_lbl("Device"))
        self._deactivate_btn = QPushButton("Deactivate this device")
        self._deactivate_btn.setFixedHeight(34)
        self._deactivate_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_RED};
                border: 1px solid {_RED}; border-radius: 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #2A1A1A; }}
        """)
        self._deactivate_btn.clicked.connect(self._deactivate)
        dlay.addWidget(self._deactivate_btn)
        self._deact_status = QLabel("")
        self._deact_status.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        dlay.addWidget(self._deact_status)
        layout.addWidget(self._deactivate_frame)

    # ── populate ──────────────────────────────────────────────────────────────
    def _load(self) -> None:
        conf = cfg.load()
        email = conf.get("user_email", "—")
        plan  = conf.get("user_plan", "free")
        n_mem = count_memories()

        self._email_lbl.setText(email)

        is_pro = plan == "pro"
        if is_pro:
            self._mem_lbl.setText(f"{n_mem} memories")
        else:
            self._mem_lbl.setText(f"{n_mem}/{FREE_MEMORY_LIMIT} memories")
        if is_pro:
            self._plan_badge.setText("PRO")
            self._plan_badge.setStyleSheet(
                f"color: {_GOLD}; background: #2D2410; border: 1px solid {_GOLD}; "
                f"border-radius: 5px; padding: 2px 8px; font-size: 11px; font-weight: bold;"
            )
        else:
            self._plan_badge.setText("FREE")
            self._plan_badge.setStyleSheet(
                f"color: {_MUTED}; background: {_SURFACE}; border: 1px solid {_BORDER}; "
                f"border-radius: 5px; padding: 2px 8px; font-size: 11px; font-weight: bold;"
            )

        self._check_frame.setVisible(not is_pro)
        self._deactivate_frame.setVisible(is_pro)
        self._check_status.setText("")
        self._deact_status.setText("")
        self.adjustSize()

    # ── subscription check ────────────────────────────────────────────────────
    def _check_subscriber(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        order_id  = self._order_input.text().strip()
        conf      = cfg.load()
        token     = conf.get("auth_token", "")
        device_id = get_device_id()
        client    = AuthClient(conf.get("api_url"))

        self._check_status.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        self._check_status.setText("Checking…")
        self._check_btn.setEnabled(False)

        def do_check():
            return client.check_subscriber(token, device_id, order_id=order_id)

        self._start_worker(do_check, self._on_check_done, self._on_check_error)

    def _on_check_done(self, result: dict) -> None:
        plan   = result.get("plan", "free")
        status = result.get("status", "")
        conf = cfg.load()
        conf["user_plan"] = plan
        # Save order_id if provided
        order_id = self._order_input.text().strip()
        if order_id:
            conf["order_id"] = order_id
        cfg.save(conf)
        self._check_btn.setEnabled(True)
        if plan == "pro":
            self._check_status.setStyleSheet(f"color: {_GREEN}; font-size: 11px;")
            self._check_status.setText("Subscription active!")
        elif status == "trial":
            trial_ends = result.get("trial_ends_on", "")
            self._check_status.setStyleSheet(f"color: {_GOLD}; font-size: 11px;")
            self._check_status.setText(f"Free trial active (ends {trial_ends})")
        else:
            self._check_status.setStyleSheet(f"color: {_RED}; font-size: 11px;")
            self._check_status.setText("No active subscription.")
        self._load()

    def _on_check_error(self, msg: str) -> None:
        self._check_btn.setEnabled(True)
        self._check_status.setStyleSheet(f"color: {_RED}; font-size: 11px;")
        self._check_status.setText(msg)

    # ── deactivation ──────────────────────────────────────────────────────────
    def _deactivate(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        conf      = cfg.load()
        token     = conf.get("auth_token", "")
        device_id = get_device_id()
        client    = AuthClient(conf.get("api_url"))

        self._deact_status.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        self._deact_status.setText("Deactivating…")
        self._deactivate_btn.setEnabled(False)

        def do_deactivate():
            client.deactivate_device(token, device_id)
            return {}

        self._start_worker(do_deactivate, self._on_deactivate_done, self._on_deactivate_error)

    def _on_deactivate_done(self, _: dict) -> None:
        conf = cfg.load()
        conf["user_plan"] = "free"
        cfg.save(conf)
        self._deactivate_btn.setEnabled(True)
        self._deact_status.setStyleSheet(f"color: {_GREEN}; font-size: 11px;")
        self._deact_status.setText("Deactivated.")
        self._load()

    def _on_deactivate_error(self, msg: str) -> None:
        self._deactivate_btn.setEnabled(True)
        self._deact_status.setStyleSheet(f"color: {_RED}; font-size: 11px;")
        self._deact_status.setText(msg)

    # ── worker helper ─────────────────────────────────────────────────────────
    def _start_worker(self, fn, on_done, on_error) -> None:
        self._thread = QThread()
        self._worker = _Worker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(on_done)
        self._worker.error.connect(on_error)
        self._worker.done.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(lambda: setattr(self, '_thread', None))
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    # ── show / hide ───────────────────────────────────────────────────────────
    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self._load()
            self._position()
            self.show()
            self.raise_()
            self.activateWindow()

    def _position(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        x = screen.right() - self.width() - 20
        y = screen.bottom() - self.height() - 60
        self.move(x, y)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)


# ── helpers ────────────────────────────────────────────────────────────────────
def _sep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color: {_BORDER};")
    return sep

def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: bold;")
    return lbl

def _input_style() -> str:
    return f"""
        QLineEdit {{
            background: {_SURFACE}; color: {_TEXT};
            border: 1px solid {_BORDER}; border-radius: 8px;
            padding: 7px 12px; font-size: 13px;
        }}
        QLineEdit:focus {{ border-color: {_ACCENT}; }}
    """

def _btn_style() -> str:
    return f"""
        QPushButton {{
            background: {_ACCENT}; color: white;
            border-radius: 8px; font-size: 12px; font-weight: bold;
        }}
        QPushButton:hover {{ background: #6D28D9; }}
        QPushButton:disabled {{ background: {_SURFACE}; color: {_MUTED}; }}
    """
