import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtCore import QEventLoop, QThread
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

# Load .env from project root (fallback to home)
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path.home() / ".sage" / ".env")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Sage")
    app.setQuitOnLastWindowClosed(False)

    # ── Step 0: tray availability ─────────────────────────────────────────────
    if not QSystemTrayIcon.isSystemTrayAvailable():
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
            pass  # use cached plan on failure

    _sync_thread = QThread()
    _sync_thread.run = _sync_license  # type: ignore[method-assign]
    _sync_thread.start()

    # ── Step 4: tray ──────────────────────────────────────────────────────────
    from ui.tray import SageTray

    tray = SageTray()
    tray.show()

    # If no order_id saved yet, open Account dialog so user can activate
    if not conf.get("order_id"):
        tray._account.toggle()
    else:
        tray.showMessage("Sage", "Ready. Click the icon to open.", tray.icon(), 2000)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
