import base64
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


BACKUP_SUFFIX = ".sagebackup"
_MAGIC = "SAGE_BACKUP_V1"
_ITERATIONS = 390_000
_MEMORY_EXPORT_NAME = "sqlite_memories.json"
_KNOWN_TOP_LEVEL_NAMES = {
    _MEMORY_EXPORT_NAME,
}


class BackupError(Exception):
    pass


def export_backup(destination: str | Path, password: str) -> Path:
    if not password:
        raise BackupError("Backup password is required.")

    try:
        from core.sqlite_memory import export_memory_snapshot, flush, reset

        flush()
        reset()
        snapshot = export_memory_snapshot()
    except Exception as exc:
        raise BackupError(f"Memory backup export failed: {exc}") from exc

    if not snapshot.get("memories"):
        raise BackupError("No local Sage memories found to export.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload = _build_backup_payload(snapshot)
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
        snapshot = _load_backup_payload(payload)
    except Exception as exc:
        raise BackupError("Backup contents could not be restored.") from exc

    try:
        from core.sqlite_memory import import_memory_snapshot, reset

        reset()
        import_memory_snapshot(snapshot)
        reset()
    except Exception as exc:
        raise BackupError(f"Backup contents could not be restored: {exc}") from exc


def _build_backup_payload(snapshot: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            _MEMORY_EXPORT_NAME,
            json.dumps(snapshot, ensure_ascii=True),
        )
    return buffer.getvalue()


def _load_backup_payload(payload: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        for info in archive.infolist():
            relative = _normalize_backup_member(info.filename)
            if relative is None:
                continue
            if relative.name != _MEMORY_EXPORT_NAME:
                continue
            with archive.open(info, "r") as src:
                return json.loads(src.read().decode("utf-8"))
    raise BackupError("Backup contents could not be restored.")


def _normalize_backup_member(name: str) -> Path | None:
    raw = name.replace("\\", "/").strip()
    if not raw:
        return None

    posix = PurePosixPath(raw)
    parts = [part for part in posix.parts if part not in ("", ".", "/")]
    if not parts:
        return None

    if ".sage" in parts:
        parts = parts[parts.index(".sage") + 1:]
    elif parts[0] not in _KNOWN_TOP_LEVEL_NAMES:
        anchor_index = next((i for i, part in enumerate(parts) if part in _KNOWN_TOP_LEVEL_NAMES), None)
        if anchor_index is not None:
            parts = parts[anchor_index:]

    if not parts:
        return None
    if any(part == ".." for part in parts):
        raise BackupError(f"Backup contains invalid path: {name}")

    relative = Path(*parts)
    if relative.name not in _KNOWN_TOP_LEVEL_NAMES:
        return None
    return relative


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
