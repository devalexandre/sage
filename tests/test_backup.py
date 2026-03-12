import base64
import io
import json
import zipfile
from pathlib import Path

from core import backup


def _write_backup(tmp_path: Path, payload: bytes, password: str) -> Path:
    token, salt = backup._encrypt_payload(payload, password)
    document = {
        "magic": backup._MAGIC,
        "created_at": "2026-03-12T00:00:00+00:00",
        "salt": base64.b64encode(salt).decode("ascii"),
        "payload": base64.b64encode(token).decode("ascii"),
    }
    target = tmp_path / "test.sagebackup"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def test_export_backup_skips_lock_files(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.json").write_text("{}", encoding="utf-8")
    (data_dir / ".milvus.db.lock").write_text("busy", encoding="utf-8")

    monkeypatch.setattr(backup, "DATA_DIR", data_dir)

    exported = backup.export_backup(tmp_path / "out.sagebackup", "secret")
    document = json.loads(exported.read_text(encoding="utf-8"))
    payload = backup._decrypt_payload(
        base64.b64decode(document["payload"]),
        base64.b64decode(document["salt"]),
        "secret",
    )

    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        assert archive.namelist() == ["config.json"]


def test_import_backup_normalizes_legacy_qdrant_paths(tmp_path, monkeypatch):
    data_dir = tmp_path / "restored"
    monkeypatch.setattr(backup, "DATA_DIR", data_dir)

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../../home/devalexandre/sage/qdrant_storage/aliases/data.json", '{"ok":true}')
        archive.writestr("/home/devalexandre/.sage/config.json", '{"language":"pt-BR"}')
        archive.writestr("../../home/devalexandre/.sage/.milvus.db.lock", "busy")

    source = _write_backup(tmp_path, payload.getvalue(), "secret")
    backup.import_backup(source, "secret")

    assert (data_dir / "config.json").read_text(encoding="utf-8") == '{"language":"pt-BR"}'
    assert (data_dir / "qdrant_storage" / "aliases" / "data.json").read_text(encoding="utf-8") == '{"ok":true}'
    assert not (data_dir / ".milvus.db.lock").exists()
