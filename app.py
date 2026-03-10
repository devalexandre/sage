import logging
import logging.handlers
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtCore import QEventLoop, QObject, QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

# Load .env from project root (fallback to home)
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path.home() / ".sage" / ".env")

# ── Logging setup ────────────────────────────────────────────────────────────
LOG_DIR = Path.home() / ".sage"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "sage.log"

_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8",
)
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger("sage")


def _exception_hook(exc_type, exc_value, exc_tb):
    """Global exception handler — log uncaught exceptions to file."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical(
        "Uncaught exception:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    )


sys.excepthook = _exception_hook


def main() -> None:
    logger.info("Sage starting...")
    app = QApplication(sys.argv)
    app.setApplicationName("Sage")
    app.setQuitOnLastWindowClosed(False)

    # ── Step 0: tray availability ─────────────────────────────────────────────
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.error("System tray is not available — exiting.")
        QMessageBox.critical(None, "Sage", "System tray is not available.")
        sys.exit(1)

    # ── Step 1: encryption bootstrap ─────────────────────────────────────────
    from core.encryption import (
        EncryptionKeyCorrupted, EncryptionKeyMissing,
        first_run_init, key_exists, load_key,
    )
    from db.sqlite import set_fernet

    if not key_exists():
        phrase = first_run_init()
        from ui.recovery import SageRecoveryDialog
        recovery = SageRecoveryDialog(phrase)
        loop = QEventLoop()
        recovery.confirmed.connect(loop.quit)
        recovery.show()
        loop.exec()

    try:
        fernet = load_key()
    except (EncryptionKeyMissing, EncryptionKeyCorrupted) as e:
        QMessageBox.critical(None, "Sage — Encryption Error", str(e))
        sys.exit(1)

    set_fernet(fernet)
    logger.info("Step 1 OK: encryption loaded.")

    # ── Step 2: auth gate ─────────────────────────────────────────────────────
    from core import config as cfg
    from core.auth_client import AuthClient, NetworkError
    from core.license import check_and_refresh_token, get_device_id

    conf   = cfg.load()
    client = AuthClient(conf.get("api_url"))

    def _has_valid_token(conf: dict) -> bool:
        return bool(conf.get("auth_token"))

    def _try_refresh(conf: dict) -> dict | None:
        try:
            return check_and_refresh_token(client, conf)
        except Exception:
            return None

    needs_login = not _has_valid_token(conf) or _try_refresh(conf) is None
    logger.info("Step 2: needs_login=%s", needs_login)

    if needs_login:
        from ui.auth import SageAuthDialog

        auth_dialog = SageAuthDialog(conf.get("api_url"))
        loop = QEventLoop()

        def _on_auth(result: dict) -> None:
            nonlocal conf
            conf["auth_token"]    = result.get("access_token", "")
            conf["refresh_token"] = result.get("refresh_token", "")
            conf["user_id"]       = result.get("user_id", "")
            conf["user_email"]    = result.get("email", "")
            conf["user_plan"]     = result.get("plan", "free")
            conf["device_id"]     = get_device_id()
            cfg.save(conf)
            loop.quit()

        auth_dialog.login_success.connect(_on_auth)
        auth_dialog.register_success.connect(_on_auth)
        auth_dialog.show()
        loop.exec()
        conf = cfg.load()  # reload after save

    # ── Step 3: subscription check (background, non-blocking) ────────────────
    def _sync_license() -> None:
        try:
            device_id = get_device_id()
            order_id = conf.get("order_id", "")
            result = client.check_subscriber(
                conf.get("auth_token", ""), device_id, order_id=order_id,
            )
            c = cfg.load()
            c["user_plan"] = result.get("plan", "free")
            cfg.save(c)
        except Exception:
            logger.warning("License sync failed: %s", traceback.format_exc())

    _sync_thread = QThread()
    _sync_thread.run = _sync_license  # type: ignore[method-assign]
    _sync_thread.start()

    # ── Step 4: tray ──────────────────────────────────────────────────────────
    logger.info("Step 4: creating tray...")
    from ui.tray import SageTray

    tray = SageTray()
    tray.show()
    logger.info("Step 4 OK: tray visible.")

    # ── Step 5: global hotkey ─────────────────────────────────────────────────
    logger.info("Step 5: starting hotkey listener...")
    from core.hotkey import HotkeyListener

    hotkey_listener = HotkeyListener(conf.get("hotkey", "F10"))
    hotkey_listener.triggered.connect(tray._open_popup)
    hotkey_listener.start()
    tray._hotkey_listener = hotkey_listener  # keep reference
    tray._settings.hotkey_changed.connect(hotkey_listener.update_hotkey)
    logger.info("Step 5 OK: hotkey listener active.")

    # ── Step 6: check for updates (background) ────────────────────────────────
    class _UpdateSignal(QObject):
        update_available = Signal(dict)

    _update_sig = _UpdateSignal()

    def _on_update(info: dict) -> None:
        title = info.get("title") or f"Sage {info['version']}"
        notes = info.get("notes", "")
        msg = f"Nova versao disponivel: {title}"
        if notes:
            msg += f"\n{notes}"
        tray.showMessage("Sage — Atualizacao", msg, tray.icon(), 8000)
        logger.info("Update available: %s", info.get("version"))

    _update_sig.update_available.connect(_on_update)

    def _check_update() -> None:
        try:
            result = client.check_update(cfg.VERSION)
            if result.get("update_available"):
                _update_sig.update_available.emit(result)
        except Exception:
            logger.debug("Update check failed: %s", traceback.format_exc())

    _update_thread = QThread()
    _update_thread.run = _check_update  # type: ignore[method-assign]
    _update_thread.start()

    # ── Step 7: migrate SQLite → Milvus (one-time, background) ──────────────
    def _run_migration() -> None:
        try:
            from core.migrate import migrate_sqlite_to_milvus
            count = migrate_sqlite_to_milvus()
            if count:
                logger.info("Migration: %d memories moved to Milvus", count)
        except Exception:
            logger.debug("Migration failed: %s", traceback.format_exc())

    _migrate_thread = QThread()
    _migrate_thread.run = _run_migration  # type: ignore[method-assign]
    _migrate_thread.start()

    # ── Step 8: forget cleanup (background) ─────────────────────────────────
    def _run_forget() -> None:
        try:
            from core.forget import run_cleanup
            result = run_cleanup()
            if result["memories_deleted"]:
                logger.info("Forget cleanup: %s", result)
        except Exception:
            logger.debug("Forget cleanup failed: %s", traceback.format_exc())

    _forget_thread = QThread()
    _forget_thread.run = _run_forget  # type: ignore[method-assign]
    _forget_thread.start()

    # If no order_id saved yet, open Account dialog so user can activate
    if not conf.get("order_id"):
        tray._account.toggle()
    else:
        tray.showMessage("Sage", "Ready. Click the icon to open.", tray.icon(), 2000)

    logger.info("Sage ready — entering event loop.")
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.critical("Fatal error in main():\n%s", traceback.format_exc())
        sys.exit(1)
