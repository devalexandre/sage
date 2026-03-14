import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import app
from core import migrate


class StartupBehaviorTests(unittest.TestCase):
    def test_should_log_to_console_when_not_frozen(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(app.sys, "frozen", new=False, create=True):
            self.assertTrue(app._should_log_to_console())

    def test_should_not_log_to_console_when_frozen_without_override(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(app.sys, "frozen", new=True, create=True):
            self.assertFalse(app._should_log_to_console())

    def test_should_log_to_console_when_env_override_is_set(self) -> None:
        with patch.dict(os.environ, {"SAGE_LOG_TO_CONSOLE": "1"}, clear=True), \
             patch.object(app.sys, "frozen", new=True, create=True):
            self.assertTrue(app._should_log_to_console())

    def test_migrate_qdrant_memories_imports_into_sqlite(self) -> None:
        rows = [{"id": "1", "content": "legacy", "meta_data": {}}]

        with patch("core.migrate._iter_qdrant_memories", return_value=rows), \
             patch("core.sqlite_memory.store") as store_mock, \
             patch("core.vault.extract_full_text", return_value="dados chamaelas\nsenha: 123456"), \
             patch("core.vault.sanitize_for_retrieval", return_value="dados chamaelas\nsenha: [PASSWORD]"):
            migrated = migrate.migrate_qdrant_memories()

        self.assertEqual(migrated, 1)
        store_mock.assert_called_once_with(
            "dados chamaelas\nsenha: [PASSWORD]",
            original_text="dados chamaelas\nsenha: 123456",
        )

    def test_migrate_legacy_sqlite_memories_uses_canonical_store(self) -> None:
        memory = Mock(memory="segredo 123", memory_id="legacy-id")
        db = Mock()
        db.get_user_memories.return_value = [memory]

        with tempfile.TemporaryDirectory() as tmp_dir:
            legacy_path = migrate.Path(tmp_dir) / "sage.db"
            legacy_path.write_text("placeholder", encoding="utf-8")

            with patch("core.migrate.LEGACY_DB_PATH", legacy_path), \
                 patch("core.migrate.SqliteDb", return_value=db), \
                 patch("core.sqlite_memory.store") as store_mock, \
                 patch("core.vault.sanitize_for_retrieval", return_value="segredo [SECRET]"), \
                 patch("core.migrate._remove_legacy_db") as remove_mock:
                migrated = migrate.migrate_legacy_sqlite_memories()

        self.assertEqual(migrated, 1)
        store_mock.assert_called_once_with("segredo [SECRET]", original_text="segredo 123")
        remove_mock.assert_called_once()

    def test_run_startup_migrations_saves_version_only_after_success(self) -> None:
        initial_conf = {"data_migration_version": 0}
        saved = {}

        def fake_load():
            return dict(initial_conf)

        def fake_save(conf):
            saved.update(conf)

        with patch("core.migrate.cfg.load", side_effect=fake_load), \
             patch("core.migrate.cfg.save", side_effect=fake_save), \
             patch("core.migrate.migrate_legacy_sqlite_memories", return_value=2), \
             patch("core.migrate.migrate_legacy_milvus_memories", return_value=3), \
             patch("core.migrate.migrate_qdrant_memories", return_value=4):
            result = migrate.run_startup_migrations()

        self.assertEqual(
            result,
            {
                "legacy_sqlite_imported": 2,
                "legacy_milvus_imported": 3,
                "qdrant_to_sqlite": 4,
            },
        )
        self.assertEqual(saved["data_migration_version"], 4)

    def test_run_startup_migrations_does_not_save_when_qdrant_step_fails(self) -> None:
        with patch("core.migrate.cfg.load", return_value={"data_migration_version": 3}), \
             patch("core.migrate.cfg.save") as save_mock, \
             patch("core.migrate.migrate_qdrant_memories", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                migrate.run_startup_migrations()

        save_mock.assert_not_called()

    def test_sanitize_qt_style_override_removes_invalid_style(self) -> None:
        with patch.dict(os.environ, {"QT_STYLE_OVERRIDE": "kvantum"}, clear=False), \
             patch("app.QStyleFactory.keys", return_value=["Windows", "Fusion"]):
            app._sanitize_qt_style_override()
            self.assertNotIn("QT_STYLE_OVERRIDE", os.environ)

    def test_sanitize_qt_style_override_keeps_valid_style(self) -> None:
        with patch.dict(os.environ, {"QT_STYLE_OVERRIDE": "Fusion"}, clear=False), \
             patch("app.QStyleFactory.keys", return_value=["Windows", "Fusion"]):
            app._sanitize_qt_style_override()
            self.assertEqual(os.environ.get("QT_STYLE_OVERRIDE"), "Fusion")

    def test_sanitize_qt_style_override_ignores_missing_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
             patch("app.QStyleFactory.keys", return_value=["Windows", "Fusion"]):
            app._sanitize_qt_style_override()
            self.assertNotIn("QT_STYLE_OVERRIDE", os.environ)


if __name__ == "__main__":
    unittest.main()
