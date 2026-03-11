import base64
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


DATA_DIR = Path.home() / ".sage"
BACKUP_SUFFIX = ".sagebackup"
_MAGIC = "SAGE_BACKUP_V1"
_ITERATIONS = 390_000


class BackupError(Exception):
    pass


def export_backup(destination: str | Path, password: str) -> Path:
    if not password:
        raise BackupError("Backup password is required.")
    if not DATA_DIR.exists():
        raise BackupError("No local Sage data found to export.")

    try:
        from core.milvus_memory import flush as flush_milvus

        flush_milvus()
    except Exception:
        pass

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload = _zip_data_dir()
    token, salt = _encrypt_payload(payload, password)
    document = {
        "magic": _MAGIC,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "salt": base64.b64encode(salt).decode("ascii"),
        "payload": base64.b64encode(token).decode("ascii"),
    }
    destination.write_text(json.dumps(document), encoding="utf-8")
    return destination


def import_backup(source: str | Path, password: str) -> None:
    if not password:
        raise BackupError("Backup password is required.")

    source = Path(source)
    if not source.exists():
        raise BackupError("Backup file not found.")

    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BackupError("Backup file is invalid or corrupted.") from exc

    if document.get("magic") != _MAGIC:
        raise BackupError("Unsupported backup format.")

    try:
        salt = base64.b64decode(document["salt"])
        token = base64.b64decode(document["payload"])
    except Exception as exc:
        raise BackupError("Backup file is invalid or corrupted.") from exc

    payload = _decrypt_payload(token, salt, password)

    try:
        from core.milvus_memory import reset as reset_milvus

        reset_milvus()
    except Exception:
        pass

    with tempfile.TemporaryDirectory(prefix="sage-import-") as temp_dir:
        restore_dir = Path(temp_dir) / "restore"
        restore_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
                archive.extractall(restore_dir)
        except Exception as exc:
            raise BackupError("Backup contents could not be restored.") from exc

        previous_dir = Path(temp_dir) / "previous"
        had_existing = DATA_DIR.exists()

        if had_existing:
            shutil.move(str(DATA_DIR), str(previous_dir))

        try:
            shutil.copytree(restore_dir, DATA_DIR)
        except Exception as exc:
            if DATA_DIR.exists():
                shutil.rmtree(DATA_DIR, ignore_errors=True)
            if had_existing and previous_dir.exists():
                shutil.move(str(previous_dir), str(DATA_DIR))
            raise BackupError("Backup contents could not be restored.") from exc


def _zip_data_dir() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DATA_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(DATA_DIR))
    return buffer.getvalue()


def _encrypt_payload(payload: bytes, password: str) -> tuple[bytes, bytes]:
    salt = os.urandom(16)
    fernet = _derive_fernet(password, salt)
    return fernet.encrypt(payload), salt


def _decrypt_payload(token: bytes, salt: bytes, password: str) -> bytes:
    fernet = _derive_fernet(password, salt)
    try:
        return fernet.decrypt(token)
    except InvalidToken as exc:
        raise BackupError("Invalid backup password or corrupted backup file.") from exc


def _derive_fernet(password: str, salt: bytes) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    return Fernet(key)
