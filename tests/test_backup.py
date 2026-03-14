import base64
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

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


def test_export_backup_contains_sqlite_memory_snapshot_only(tmp_path):
    snapshot = {
        "format": "agno_sqlite_memory_v1",
        "memories": [{"id": "1", "content": "mem", "meta_data": {"created_at": 1}}],
    }
    with patch("core.sqlite_memory.flush"), \
         patch("core.sqlite_memory.reset"), \
         patch("core.sqlite_memory.export_memory_snapshot", return_value=snapshot):
        exported = backup.export_backup(tmp_path / "out.sagebackup", "secret")
    document = json.loads(exported.read_text(encoding="utf-8"))
    payload = backup._decrypt_payload(
        base64.b64decode(document["payload"]),
        base64.b64decode(document["salt"]),
        "secret",
    )

    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        assert archive.namelist() == ["sqlite_memories.json"]


def test_import_backup_normalizes_legacy_memory_export_paths(tmp_path):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "/home/devalexandre/.sage/sqlite_memories.json",
            json.dumps({"format": "agno_sqlite_memory_v1", "memories": []}),
        )
        archive.writestr("/home/devalexandre/.sage/config.json", '{"language":"pt-BR"}')

    source = _write_backup(tmp_path, payload.getvalue(), "secret")
    with patch("core.sqlite_memory.reset"), \
         patch("core.sqlite_memory.import_memory_snapshot") as import_mock:
        backup.import_backup(source, "secret")

    import_mock.assert_called_once_with({"format": "agno_sqlite_memory_v1", "memories": []})


def test_import_backup_restores_memory_snapshot_only(tmp_path):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "sqlite_memories.json",
            json.dumps(
                {
                    "format": "agno_sqlite_memory_v1",
                    "memories": [{"id": "abc", "content": "note", "meta_data": {"created_at": 1}}],
                }
            ),
        )

    source = _write_backup(tmp_path, payload.getvalue(), "secret")
    with patch("core.sqlite_memory.reset"), \
         patch("core.sqlite_memory.import_memory_snapshot") as import_mock:
        backup.import_backup(source, "secret")

    import_mock.assert_called_once()
