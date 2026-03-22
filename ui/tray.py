from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ui.account import SageAccount
from ui.popup import SagePopup
from ui.settings import SageSettings


class SageTray(QSystemTrayIcon):
    def __init__(self) -> None:
        super().__init__(_build_icon())
        self.setToolTip("Sage")

        self._before_open_popup = None
        self._popup    = SagePopup()
        self._settings = SageSettings()
        self._account  = SageAccount()
        self._build_context_menu()
        self.activated.connect(self._on_activated)

    # ------------------------------------------------------------------
    @staticmethod
    def is_available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    # ------------------------------------------------------------------
    def _build_context_menu(self) -> None:
        menu = QMenu()
        menu.addAction("Open Sage",  self._open_popup)
        menu.addAction("Settings",   self._open_settings)
        menu.addAction("Account",    self._open_account)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.quit)
        self.setContextMenu(menu)

    def set_before_open_popup(self, callback) -> None:
        self._before_open_popup = callback

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open_popup()

    def _open_popup(self) -> None:
        if self._before_open_popup is not None and self._before_open_popup():
            return
        self._settings.hide()
        self._account.hide()
        self._popup.toggle()

    def _open_settings(self) -> None:
        self._popup.hide()
        self._account.hide()
        self._settings.toggle()

    def _open_account(self) -> None:
        self._popup.hide()
        self._settings.hide()
        self._account.toggle()


# ----------------------------------------------------------------------
def _build_icon() -> QIcon:
    size = 32
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#7C3AED"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.setPen(QColor("#FFFFFF"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(16)
    painter.setFont(font)
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    painter.end()
    return QIcon(px)
