from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

_BG = "#1E1E2E"
_SURFACE = "#313244"
_BORDER = "#45475A"
_TEXT = "#CDD6F4"
_MUTED = "#6C7086"
_ACCENT = "#7C3AED"
_BLUE = "#1E2D40"
_BLUE_TEXT = "#89B4FA"

_COPY = {
    "pt-BR": {
        "title": "Bem-vindo ao Sage",
        "intro": (
            "O Sage roda na bandeja do sistema. Antes de usar o chat, voce precisa "
            "configurar sua OpenAI API key."
        ),
        "steps": (
            "1. Localize o icone do Sage na barra de tarefas.\n"
            "2. Clique com o botao direito no icone.\n"
            "3. Abra Settings.\n"
            "4. Cole sua OpenAI API key e clique em Save.\n"
            "5. No chat: textos sem ? sao salvos na memoria; textos com ? fazem perguntas."
        ),
        "note": "Voce tambem pode clicar no icone para abrir o chat rapidamente.",
        "dont_show_again": "Nao mostrar novamente",
        "open_settings": "Abrir Settings",
        "continue": "Continuar",
    },
    "en": {
        "title": "Welcome to Sage",
        "intro": (
            "Sage runs from the system tray. Before using chat, configure your "
            "OpenAI API key."
        ),
        "steps": (
            "1. Find the Sage icon in the taskbar tray.\n"
            "2. Right-click the icon.\n"
            "3. Open Settings.\n"
            "4. Paste your OpenAI API key and click Save.\n"
            "5. In chat: messages without ? are saved to memory; messages with ? ask questions."
        ),
        "note": "You can also click the icon to open chat quickly.",
        "dont_show_again": "Don't show this again",
        "open_settings": "Open Settings",
        "continue": "Continue",
    },
    "es": {
        "title": "Bienvenido a Sage",
        "intro": (
            "Sage se ejecuta en la bandeja del sistema. Antes de usar el chat, "
            "configura tu OpenAI API key."
        ),
        "steps": (
            "1. Busca el icono de Sage en la barra de tareas.\n"
            "2. Haz clic derecho en el icono.\n"
            "3. Abre Settings.\n"
            "4. Pega tu OpenAI API key y haz clic en Save.\n"
            "5. En el chat: mensajes sin ? se guardan en memoria; mensajes con ? hacen preguntas."
        ),
        "note": "Tambien puedes hacer clic en el icono para abrir el chat rapidamente.",
        "dont_show_again": "No mostrar de nuevo",
        "open_settings": "Abrir Settings",
        "continue": "Continuar",
    },
}


class SageOnboardingDialog(QWidget):
    completed = Signal()
    open_settings_requested = Signal()

    def __init__(self, language: str = "pt-BR") -> None:
        super().__init__()
        self._copy = _COPY["en"]
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(500)
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

        title = QLabel(self._copy["title"])
        title.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_TEXT};")
        layout.addWidget(title)

        intro = QLabel(self._copy["intro"])
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        layout.addWidget(intro)

        steps = QLabel(self._copy["steps"])
        steps.setWordWrap(True)
        steps.setStyleSheet(f"""
            color: {_BLUE_TEXT};
            background: {_BLUE};
            border: 1px solid {_BORDER};
            border-radius: 10px;
            padding: 12px;
            font-size: 12px;
        """)
        layout.addWidget(steps)

        note = QLabel(self._copy["note"])
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        layout.addWidget(note)

        self._dont_show_again = QCheckBox(self._copy["dont_show_again"])
        self._dont_show_again.setChecked(False)
        self._dont_show_again.setStyleSheet(f"""
            QCheckBox {{
                color: {_TEXT}; font-size: 12px; spacing: 8px;
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
        layout.addWidget(self._dont_show_again)

        open_settings_btn = QPushButton(self._copy["open_settings"])
        open_settings_btn.setFixedHeight(38)
        open_settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white;
                border-radius: 8px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #6D28D9; }}
        """)
        open_settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(open_settings_btn)

        continue_btn = QPushButton(self._copy["continue"])
        continue_btn.setFixedHeight(34)
        continue_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_SURFACE}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        continue_btn.clicked.connect(self._complete)
        layout.addWidget(continue_btn)

    def _open_settings(self) -> None:
        self.open_settings_requested.emit()
        self._complete()

    def _complete(self) -> None:
        self.completed.emit()
        self.hide()

    def skip_future_onboarding(self) -> bool:
        return self._dont_show_again.isChecked()

    def _center(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )

    def position_near(self, anchor: QWidget | None) -> None:
        if anchor is None or not anchor.isVisible():
            self._center()
            return

        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        margin = 20
        x = anchor.x() - self.width() - margin
        if x < screen.left() + margin:
            x = screen.left() + margin
        y = anchor.y()
        max_y = screen.bottom() - self.height() - margin
        y = max(screen.top() + margin, min(y, max_y))
        self.move(x, y)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            return
        super().keyPressEvent(event)
