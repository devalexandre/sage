import importlib.util
import json
import platform
import sys
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import config as cfg

_OS = platform.system()  # "Linux", "Darwin", "Windows"

OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
    "o1-mini",
    "o1",
]


# ── provider availability checks ──────────────────────────────────────────────

def _ollama_available() -> bool:
    """True if the 'ollama' Python package is installed."""
    return importlib.util.find_spec("ollama") is not None


def _lmstudio_available() -> bool:
    """True if an LM Studio server is reachable at the configured (or default) URL."""
    base_url = cfg.load().get("lmstudio_base_url", "http://127.0.0.1:1234/v1")
    url = base_url.rstrip("/") + "/models"
    try:
        urllib.request.urlopen(url, timeout=1)
        return True
    except Exception:
        return False


# Each entry: (display label, config key, availability_fn | None)
_ALL_PROVIDERS = [
    ("OpenAI",    "openai",    None),
    ("Ollama",    "ollama",    _ollama_available),
    ("LM Studio", "lmstudio",  _lmstudio_available),
]


# ── model fetching (background thread) ────────────────────────────────────────

def _fetch_ollama_models(host: str) -> list[str]:
    url = host.rstrip("/") + "/api/tags"
    with urllib.request.urlopen(url, timeout=4) as resp:
        data = json.loads(resp.read())
    return [m["name"] for m in data.get("models", [])]


def _fetch_lmstudio_models(base_url: str) -> list[str]:
    url = base_url.rstrip("/") + "/models"
    with urllib.request.urlopen(url, timeout=4) as resp:
        data = json.loads(resp.read())
    return [m["id"] for m in data.get("data", [])]


class _ModelFetcher(QObject):
    done  = Signal(list)
    error = Signal(str)

    def __init__(self, provider: str, url: str) -> None:
        super().__init__()
        self._provider = provider
        self._url = url

    def run(self) -> None:
        try:
            if self._provider == "ollama":
                models = _fetch_ollama_models(self._url)
            else:
                models = _fetch_lmstudio_models(self._url)
            self.done.emit(models)
        except Exception as exc:
            self.error.emit(str(exc))


# ── autostart helpers ──────────────────────────────────────────────────────────

def _resolve_exec() -> str:
    sage_bin = Path(sys.executable).parent / ("sage.exe" if _OS == "Windows" else "sage")
    if sage_bin.exists():
        return str(sage_bin)
    app_py = Path(__file__).parent.parent / "app.py"
    return f"{sys.executable} {app_py}"


# Linux
_DESKTOP_DIR  = Path.home() / ".config" / "autostart"
_DESKTOP_FILE = _DESKTOP_DIR / "sage.desktop"
_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=Sage
Comment=Personal knowledge widget
Exec={exec_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""

def _linux_enabled() -> bool:
    return _DESKTOP_FILE.exists()

def _linux_set(enabled: bool) -> None:
    if enabled:
        _DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
        _DESKTOP_FILE.write_text(_DESKTOP_TEMPLATE.format(exec_path=_resolve_exec()))
    else:
        _DESKTOP_FILE.unlink(missing_ok=True)


# Windows
_WIN_REG_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_WIN_APP_NAME = "Sage"

def _windows_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_REG_KEY) as key:
            winreg.QueryValueEx(key, _WIN_APP_NAME)
        return True
    except Exception:
        return False

def _windows_set(enabled: bool) -> None:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _WIN_REG_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, _WIN_APP_NAME, 0, winreg.REG_SZ, _resolve_exec())
            else:
                winreg.DeleteValue(key, _WIN_APP_NAME)
    except Exception:
        pass


# macOS
_PLIST_DIR  = Path.home() / "Library" / "LaunchAgents"
_PLIST_FILE = _PLIST_DIR / "com.sage.app.plist"
_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.sage.app</string>
  <key>ProgramArguments</key>
  <array><string>{exec_path}</string></array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
"""

def _macos_enabled() -> bool:
    return _PLIST_FILE.exists()

def _macos_set(enabled: bool) -> None:
    if enabled:
        _PLIST_DIR.mkdir(parents=True, exist_ok=True)
        _PLIST_FILE.write_text(_PLIST_TEMPLATE.format(exec_path=_resolve_exec()))
    else:
        _PLIST_FILE.unlink(missing_ok=True)


def _autostart_enabled() -> bool:
    if _OS == "Windows": return _windows_enabled()
    if _OS == "Darwin":  return _macos_enabled()
    return _linux_enabled()

def _set_autostart(enabled: bool) -> None:
    if _OS == "Windows":   _windows_set(enabled)
    elif _OS == "Darwin":  _macos_set(enabled)
    else:                  _linux_set(enabled)


# ── palette ───────────────────────────────────────────────────────────────────
_BG      = "#1E1E2E"
_SURFACE = "#313244"
_BORDER  = "#45475A"
_TEXT    = "#CDD6F4"
_MUTED   = "#6C7086"
_ACCENT  = "#7C3AED"
_GREEN   = "#A6E3A1"
_RED     = "#F38BA8"


# ── settings window ───────────────────────────────────────────────────────────
class SageSettings(QWidget):
    hotkey_changed = Signal(str)

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
        # list of (label, key) that are currently shown in the combo
        self._visible_providers: list[tuple[str, str]] = []
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

        # title
        title_row = QHBoxLayout()
        title = QLabel("Settings")
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

        layout.addWidget(_separator())

        # General
        layout.addWidget(_section_label("General"))
        self._startup_cb = QCheckBox("Start with system")
        self._startup_cb.setChecked(_autostart_enabled())
        self._startup_cb.setStyleSheet(_checkbox_style())
        self._startup_cb.toggled.connect(_set_autostart)
        layout.addWidget(self._startup_cb)

        # Hotkey
        hotkey_row = QHBoxLayout()
        hotkey_row.addWidget(_field_label("Hotkey"))
        self._hotkey_input = _HotkeyCapture()
        self._hotkey_input.setStyleSheet(_input_style())
        self._hotkey_input.setPlaceholderText("Press a key…")
        self._hotkey_input.setFixedWidth(140)
        hotkey_row.addWidget(self._hotkey_input)
        self._hotkey_save_btn = QPushButton("Save")
        self._hotkey_save_btn.setFixedSize(50, 34)
        self._hotkey_save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: white;
                border-radius: 8px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #6D28D9; }}
        """)
        self._hotkey_save_btn.clicked.connect(self._save_hotkey)
        hotkey_row.addWidget(self._hotkey_save_btn)
        layout.addLayout(hotkey_row)
        self._hotkey_status = QLabel("")
        self._hotkey_status.setStyleSheet(f"color: {_GREEN}; font-size: 11px;")
        layout.addWidget(self._hotkey_status)

        layout.addWidget(_separator())

        # Provider selector
        layout.addWidget(_section_label("Provider"))
        self._provider_combo = QComboBox()
        self._provider_combo.setStyleSheet(_combo_style())
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        layout.addWidget(self._provider_combo)

        layout.addWidget(_separator())

        # ── OpenAI panel ──────────────────────────────────────────────────────
        self._openai_frame = QFrame()
        olay = QVBoxLayout(self._openai_frame)
        olay.setContentsMargins(0, 0, 0, 0)
        olay.setSpacing(6)

        olay.addWidget(_field_label("API Key"))
        key_row = QHBoxLayout()
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("sk-…")
        self._key_input.setStyleSheet(_input_style())
        key_row.addWidget(self._key_input)
        self._eye_btn = QPushButton("👁")
        self._eye_btn.setFixedSize(34, 34)
        self._eye_btn.setCheckable(True)
        self._eye_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_SURFACE}; border: 1px solid {_BORDER};
                border-radius: 8px; font-size: 14px;
            }}
            QPushButton:checked {{ border-color: {_ACCENT}; }}
            QPushButton:hover   {{ border-color: {_TEXT}; }}
        """)
        self._eye_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._eye_btn)
        olay.addLayout(key_row)

        olay.addWidget(_field_label("Model"))
        self._openai_model_combo = QComboBox()
        self._openai_model_combo.addItems(OPENAI_MODELS)
        self._openai_model_combo.setStyleSheet(_combo_style())
        olay.addWidget(self._openai_model_combo)

        self._openai_save_btn, self._openai_status = _save_row(olay)
        self._openai_save_btn.clicked.connect(self._save_openai)
        layout.addWidget(self._openai_frame)

        # ── Ollama panel ──────────────────────────────────────────────────────
        self._ollama_frame = QFrame()
        allay = QVBoxLayout(self._ollama_frame)
        allay.setContentsMargins(0, 0, 0, 0)
        allay.setSpacing(6)

        allay.addWidget(_field_label("Host"))
        self._ollama_host = QLineEdit()
        self._ollama_host.setPlaceholderText("http://localhost:11434")
        self._ollama_host.setStyleSheet(_input_style())
        allay.addWidget(self._ollama_host)

        allay.addWidget(_field_label("Model"))
        ollama_model_row = QHBoxLayout()
        self._ollama_model_combo = QComboBox()
        self._ollama_model_combo.setStyleSheet(_combo_style())
        ollama_model_row.addWidget(self._ollama_model_combo)
        ollama_refresh = QPushButton("↻")
        ollama_refresh.setFixedSize(34, 34)
        ollama_refresh.setToolTip("Fetch installed models from Ollama")
        ollama_refresh.setStyleSheet(_refresh_btn_style())
        ollama_refresh.clicked.connect(self._refresh_ollama)
        ollama_model_row.addWidget(ollama_refresh)
        allay.addLayout(ollama_model_row)

        self._ollama_save_btn, self._ollama_status = _save_row(allay)
        self._ollama_save_btn.clicked.connect(self._save_ollama)
        layout.addWidget(self._ollama_frame)

        # ── LM Studio panel ───────────────────────────────────────────────────
        self._lmstudio_frame = QFrame()
        llay = QVBoxLayout(self._lmstudio_frame)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(6)

        llay.addWidget(_field_label("Base URL"))
        self._lmstudio_url = QLineEdit()
        self._lmstudio_url.setPlaceholderText("http://127.0.0.1:1234/v1")
        self._lmstudio_url.setStyleSheet(_input_style())
        llay.addWidget(self._lmstudio_url)

        llay.addWidget(_field_label("Model"))
        lm_model_row = QHBoxLayout()
        self._lmstudio_model_combo = QComboBox()
        self._lmstudio_model_combo.setStyleSheet(_combo_style())
        lm_model_row.addWidget(self._lmstudio_model_combo)
        lm_refresh = QPushButton("↻")
        lm_refresh.setFixedSize(34, 34)
        lm_refresh.setToolTip("Fetch loaded models from LM Studio")
        lm_refresh.setStyleSheet(_refresh_btn_style())
        lm_refresh.clicked.connect(self._refresh_lmstudio)
        lm_model_row.addWidget(lm_refresh)
        llay.addLayout(lm_model_row)

        self._lmstudio_save_btn, self._lmstudio_status = _save_row(llay)
        self._lmstudio_save_btn.clicked.connect(self._save_lmstudio)
        layout.addWidget(self._lmstudio_frame)

        layout.addWidget(_separator())

        # ── Documents (RAG) panel ────────────────────────────────────────────
        layout.addWidget(_section_label("Documents (RAG)"))

        self._docs_frame = QFrame()
        dlay = QVBoxLayout(self._docs_frame)
        dlay.setContentsMargins(0, 0, 0, 0)
        dlay.setSpacing(6)

        # Documents folder
        dlay.addWidget(_field_label("Documents Folder"))
        docs_row = QHBoxLayout()
        self._docs_path_input = QLineEdit()
        self._docs_path_input.setPlaceholderText("~/Documents/Sage")
        self._docs_path_input.setStyleSheet(_input_style())
        docs_row.addWidget(self._docs_path_input)
        docs_browse = QPushButton("...")
        docs_browse.setFixedSize(34, 34)
        docs_browse.setStyleSheet(_refresh_btn_style())
        docs_browse.setToolTip("Browse for folder")
        docs_browse.clicked.connect(self._browse_docs_folder)
        docs_row.addWidget(docs_browse)
        dlay.addLayout(docs_row)

        # Embedder provider
        dlay.addWidget(_field_label("Embedder Provider"))
        self._embed_provider_combo = QComboBox()
        self._embed_provider_combo.addItems(["OpenAI", "Ollama"])
        self._embed_provider_combo.setStyleSheet(_combo_style())
        self._embed_provider_combo.currentIndexChanged.connect(self._on_embed_provider_changed)
        dlay.addWidget(self._embed_provider_combo)

        # Embedder model
        dlay.addWidget(_field_label("Embedder Model"))
        self._embed_model_input = QLineEdit()
        self._embed_model_input.setPlaceholderText("text-embedding-3-small")
        self._embed_model_input.setStyleSheet(_input_style())
        dlay.addWidget(self._embed_model_input)

        # Embedding dimensions
        dlay.addWidget(_field_label("Embedding Dimensions"))
        self._embed_dims_input = QLineEdit()
        self._embed_dims_input.setPlaceholderText("1536")
        self._embed_dims_input.setStyleSheet(_input_style())
        dlay.addWidget(self._embed_dims_input)

        # Qdrant URL
        dlay.addWidget(_field_label("Qdrant URL"))
        self._qdrant_url_input = QLineEdit()
        self._qdrant_url_input.setPlaceholderText("https://your-cluster.qdrant.io:6333")
        self._qdrant_url_input.setStyleSheet(_input_style())
        dlay.addWidget(self._qdrant_url_input)

        # Qdrant API Key
        dlay.addWidget(_field_label("Qdrant API Key"))
        qdrant_key_row = QHBoxLayout()
        self._qdrant_key_input = QLineEdit()
        self._qdrant_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._qdrant_key_input.setPlaceholderText("Your Qdrant API key")
        self._qdrant_key_input.setStyleSheet(_input_style())
        qdrant_key_row.addWidget(self._qdrant_key_input)
        self._qdrant_eye_btn = QPushButton("\U0001f441")
        self._qdrant_eye_btn.setFixedSize(34, 34)
        self._qdrant_eye_btn.setCheckable(True)
        self._qdrant_eye_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_SURFACE}; border: 1px solid {_BORDER};
                border-radius: 8px; font-size: 14px;
            }}
            QPushButton:checked {{ border-color: {_ACCENT}; }}
            QPushButton:hover   {{ border-color: {_TEXT}; }}
        """)
        self._qdrant_eye_btn.toggled.connect(self._toggle_qdrant_key_visibility)
        qdrant_key_row.addWidget(self._qdrant_eye_btn)
        dlay.addLayout(qdrant_key_row)

        # Qdrant Collection
        dlay.addWidget(_field_label("Collection Name"))
        self._qdrant_collection_input = QLineEdit()
        self._qdrant_collection_input.setPlaceholderText("sage_documents")
        self._qdrant_collection_input.setStyleSheet(_input_style())
        dlay.addWidget(self._qdrant_collection_input)

        self._docs_save_btn, self._docs_status = _save_row(dlay)
        self._docs_save_btn.clicked.connect(self._save_docs)
        layout.addWidget(self._docs_frame)

    # ── provider combo rebuild ─────────────────────────────────────────────────
    def _rebuild_provider_combo(self, current_key: str) -> None:
        """Re-populate the provider combo based on what is currently available."""
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()
        self._visible_providers = []

        for label, key, check_fn in _ALL_PROVIDERS:
            if check_fn is None or check_fn():
                self._provider_combo.addItem(label)
                self._visible_providers.append((label, key))

        # Restore selection (fall back to openai if the saved provider disappeared)
        idx = next((i for i, (_, k) in enumerate(self._visible_providers)
                    if k == current_key), 0)
        self._provider_combo.setCurrentIndex(idx)
        self._provider_combo.blockSignals(False)
        self._on_provider_changed(idx)

    # ── provider panel switching ───────────────────────────────────────────────
    def _on_provider_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._visible_providers):
            return
        _, key = self._visible_providers[index]
        self._openai_frame.setVisible(key == "openai")
        self._ollama_frame.setVisible(key == "ollama")
        self._lmstudio_frame.setVisible(key == "lmstudio")
        self.adjustSize()

    def _current_provider_key(self) -> str:
        idx = self._provider_combo.currentIndex()
        if 0 <= idx < len(self._visible_providers):
            return self._visible_providers[idx][1]
        return "openai"

    # ── model refresh ─────────────────────────────────────────────────────────
    def _start_fetch(self, provider: str, url: str,
                     combo: QComboBox, status: QLabel) -> None:
        if self._thread and self._thread.isRunning():
            return
        status.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        status.setText("Fetching models…")

        self._thread  = QThread()
        self._fetcher = _ModelFetcher(provider, url)
        self._fetcher.moveToThread(self._thread)
        self._thread.started.connect(self._fetcher.run)

        def on_done(models: list) -> None:
            combo.clear()
            if models:
                combo.addItems(models)
                status.setStyleSheet(f"color: {_GREEN}; font-size: 11px;")
                status.setText(f"{len(models)} model(s) found.")
            else:
                status.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
                status.setText("No models found.")
            self._thread.quit()

        def on_error(msg: str) -> None:
            status.setStyleSheet(f"color: {_RED}; font-size: 11px;")
            status.setText(f"Error: {msg}")
            self._thread.quit()

        self._fetcher.done.connect(on_done)
        self._fetcher.error.connect(on_error)
        self._thread.start()

    def _refresh_ollama(self) -> None:
        host = self._ollama_host.text().strip() or "http://localhost:11434"
        self._start_fetch("ollama", host, self._ollama_model_combo, self._ollama_status)

    def _refresh_lmstudio(self) -> None:
        url = self._lmstudio_url.text().strip() or "http://127.0.0.1:1234/v1"
        self._start_fetch("lmstudio", url, self._lmstudio_model_combo, self._lmstudio_status)

    # ── key visibility ────────────────────────────────────────────────────────
    def _toggle_key_visibility(self, visible: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self._key_input.setEchoMode(mode)

    # ── save handlers ─────────────────────────────────────────────────────────
    def _save_and_reset(self, patch: dict, status: QLabel) -> None:
        conf = cfg.load()
        conf.update(patch)
        cfg.save(conf)
        from core.agent import reset_agent
        reset_agent()
        status.setStyleSheet(f"color: {_GREEN}; font-size: 11px;")
        status.setText("Saved.")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: status.setText(""))

    def _save_openai(self) -> None:
        self._save_and_reset({
            "provider": "openai",
            "openai_api_key": self._key_input.text().strip(),
            "openai_model":   self._openai_model_combo.currentText(),
        }, self._openai_status)

    def _save_ollama(self) -> None:
        self._save_and_reset({
            "provider":    "ollama",
            "ollama_host": self._ollama_host.text().strip() or "http://localhost:11434",
            "ollama_model": self._ollama_model_combo.currentText(),
        }, self._ollama_status)

    def _save_hotkey(self) -> None:
        hotkey = self._hotkey_input.text().strip()
        if not hotkey:
            return
        conf = cfg.load()
        conf["hotkey"] = hotkey
        cfg.save(conf)
        self.hotkey_changed.emit(hotkey)
        self._hotkey_status.setStyleSheet(f"color: {_GREEN}; font-size: 11px;")
        self._hotkey_status.setText(f"Saved: {hotkey}")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self._hotkey_status.setText(""))

    def _save_lmstudio(self) -> None:
        self._save_and_reset({
            "provider":          "lmstudio",
            "lmstudio_base_url": self._lmstudio_url.text().strip() or "http://127.0.0.1:1234/v1",
            "lmstudio_model":    self._lmstudio_model_combo.currentText(),
        }, self._lmstudio_status)

    # ── Documents (RAG) handlers ─────────────────────────────────────────────
    def _browse_docs_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select documents folder")
        if folder:
            self._docs_path_input.setText(folder)

    def _on_embed_provider_changed(self, index: int) -> None:
        is_ollama = self._embed_provider_combo.currentText() == "Ollama"
        placeholder = "nomic-embed-text" if is_ollama else "text-embedding-3-small"
        self._embed_model_input.setPlaceholderText(placeholder)

    def _toggle_qdrant_key_visibility(self, visible: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self._qdrant_key_input.setEchoMode(mode)

    def _save_docs(self) -> None:
        embed_provider = "ollama" if self._embed_provider_combo.currentText() == "Ollama" else "openai"
        dims = self._embed_dims_input.text().strip()
        try:
            dims_int = int(dims) if dims else 1536
        except ValueError:
            dims_int = 1536
        self._save_and_reset({
            "documents_path":    self._docs_path_input.text().strip(),
            "embed_provider":    embed_provider,
            "embed_model":       self._embed_model_input.text().strip() or ("text-embedding-3-small" if embed_provider == "openai" else "nomic-embed-text"),
            "embed_dimensions":  dims_int,
            "qdrant_url":        self._qdrant_url_input.text().strip(),
            "qdrant_api_key":    self._qdrant_key_input.text().strip(),
            "qdrant_collection": self._qdrant_collection_input.text().strip() or "sage_documents",
        }, self._docs_status)

    # ── load fields ───────────────────────────────────────────────────────────
    def _load_fields(self) -> None:
        conf = cfg.load()

        # Hotkey
        self._hotkey_input.setText(conf.get("hotkey", "F10"))

        # Rebuild provider combo (availability may have changed since last open)
        self._rebuild_provider_combo(conf.get("provider", "openai"))

        # OpenAI
        self._key_input.setText(conf.get("openai_api_key", ""))
        oi = self._openai_model_combo.findText(conf.get("openai_model", OPENAI_MODELS[0]))
        self._openai_model_combo.setCurrentIndex(oi if oi >= 0 else 0)

        # Ollama
        self._ollama_host.setText(conf.get("ollama_host", "http://localhost:11434"))
        saved_ollama = conf.get("ollama_model", "")
        if saved_ollama:
            if self._ollama_model_combo.findText(saved_ollama) < 0:
                self._ollama_model_combo.addItem(saved_ollama)
            self._ollama_model_combo.setCurrentText(saved_ollama)

        # LM Studio
        self._lmstudio_url.setText(conf.get("lmstudio_base_url", "http://127.0.0.1:1234/v1"))
        saved_lm = conf.get("lmstudio_model", "")
        if saved_lm:
            if self._lmstudio_model_combo.findText(saved_lm) < 0:
                self._lmstudio_model_combo.addItem(saved_lm)
            self._lmstudio_model_combo.setCurrentText(saved_lm)

        # Documents (RAG)
        self._docs_path_input.setText(conf.get("documents_path", ""))
        embed_prov = conf.get("embed_provider", "openai")
        self._embed_provider_combo.setCurrentIndex(1 if embed_prov == "ollama" else 0)
        self._embed_model_input.setText(conf.get("embed_model", ""))
        dims = conf.get("embed_dimensions", 1536)
        self._embed_dims_input.setText(str(dims) if dims else "")
        self._qdrant_url_input.setText(conf.get("qdrant_url", ""))
        self._qdrant_key_input.setText(conf.get("qdrant_api_key", ""))
        self._qdrant_collection_input.setText(conf.get("qdrant_collection", "sage_documents"))

    # ── show / hide ───────────────────────────────────────────────────────────
    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self._startup_cb.setChecked(_autostart_enabled())
            self._load_fields()
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

    # ── keyboard ──────────────────────────────────────────────────────────────
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)


# ── widget helpers ─────────────────────────────────────────────────────────────
def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color: {_BORDER};")
    return sep

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: bold;")
    return lbl

def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
    return lbl

def _save_row(layout: QVBoxLayout) -> tuple[QPushButton, QLabel]:
    btn = QPushButton("Save")
    btn.setFixedHeight(36)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {_ACCENT}; color: white;
            border-radius: 8px; font-size: 13px; font-weight: bold;
        }}
        QPushButton:hover   {{ background: #6D28D9; }}
        QPushButton:pressed {{ background: #5B21B6; }}
    """)
    layout.addWidget(btn)
    status = QLabel("")
    status.setStyleSheet(f"color: {_GREEN}; font-size: 11px;")
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(status)
    return btn, status

def _input_style() -> str:
    return f"""
        QLineEdit {{
            background: {_SURFACE};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            border-radius: 8px;
            padding: 7px 12px;
            font-size: 13px;
        }}
        QLineEdit:focus {{ border-color: {_ACCENT}; }}
    """

def _combo_style() -> str:
    return f"""
        QComboBox {{
            background: {_SURFACE};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 13px;
        }}
        QComboBox:focus {{ border-color: {_ACCENT}; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{ width: 10px; height: 10px; }}
        QComboBox QAbstractItemView {{
            background: {_SURFACE};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            selection-background-color: {_ACCENT};
        }}
    """

def _refresh_btn_style() -> str:
    return f"""
        QPushButton {{
            background: {_SURFACE};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            border-radius: 8px;
            font-size: 16px;
        }}
        QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
    """

class _HotkeyCapture(QLineEdit):
    """A QLineEdit that captures key presses and displays them as hotkey strings."""

    _QT_MOD_NAMES = {
        Qt.KeyboardModifier.ControlModifier: "Ctrl",
        Qt.KeyboardModifier.AltModifier: "Alt",
        Qt.KeyboardModifier.ShiftModifier: "Shift",
        Qt.KeyboardModifier.MetaModifier: "Super",
    }

    _QT_KEY_NAMES: dict[int, str] = {
        **{getattr(Qt.Key, f"Key_F{i}"): f"F{i}" for i in range(1, 21)},
        Qt.Key.Key_Escape: "ESC",
        Qt.Key.Key_Tab: "TAB",
        Qt.Key.Key_Space: "SPACE",
        Qt.Key.Key_Return: "ENTER",
        Qt.Key.Key_Backspace: "BACKSPACE",
        Qt.Key.Key_Delete: "DELETE",
        Qt.Key.Key_Insert: "INSERT",
        Qt.Key.Key_Home: "HOME",
        Qt.Key.Key_End: "END",
        Qt.Key.Key_PageUp: "PAGEUP",
        Qt.Key.Key_PageDown: "PAGEDOWN",
        Qt.Key.Key_Up: "UP",
        Qt.Key.Key_Down: "DOWN",
        Qt.Key.Key_Left: "LEFT",
        Qt.Key.Key_Right: "RIGHT",
        Qt.Key.Key_Print: "PRINTSCREEN",
        Qt.Key.Key_Pause: "PAUSE",
    }

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()

        # Ignore standalone modifier presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        parts: list[str] = []
        for mod, name in self._QT_MOD_NAMES.items():
            if mods & mod:
                parts.append(name)

        key_name = self._QT_KEY_NAMES.get(key)
        if key_name is None:
            text = event.text().upper()
            key_name = text if len(text) == 1 and text.isprintable() else None

        if key_name:
            parts.append(key_name)
            self.setText("+".join(parts))


def _checkbox_style() -> str:
    return f"""
        QCheckBox {{
            color: {_TEXT};
            font-size: 13px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border: 1px solid {_BORDER};
            border-radius: 4px;
            background: {_SURFACE};
        }}
        QCheckBox::indicator:checked {{
            background: {_ACCENT};
            border-color: {_ACCENT};
        }}
    """
