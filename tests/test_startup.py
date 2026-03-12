import os
import unittest
from unittest.mock import Mock, patch

import app
from core import migrate


class _FakeIterator:
    def __init__(self, batches):
        self._batches = list(batches)
        self.closed = False

    def next(self):
        if self._batches:
            return self._batches.pop(0)
        return []

    def close(self):
        self.closed = True


class StartupBehaviorTests(unittest.TestCase):
    def test_migrate_legacy_memories_uses_query_iterator(self) -> None:
        iterator = _FakeIterator(
            [
                [{"id": "1", "content": "legacy", "meta_data": {}}],
                [],
            ]
        )
        client = Mock()
        client.query_iterator.return_value = iterator
        db = Mock()
        db.collection = "sage_memories"
        db.client = client

        with patch("core.milvus_memory.get_milvus", return_value=db), \
             patch("core.milvus_memory.flush") as flush_mock, \
             patch("core.milvus_memory.upsert_memory") as upsert_mock, \
             patch("core.vault.extract_full_text", return_value="dados chamaelas\nsenha: 123456"), \
             patch("core.vault.sanitize_for_retrieval", return_value="dados chamaelas\nsenha: [PASSWORD]"):
            migrated = migrate.migrate_legacy_milvus_memories()

        self.assertEqual(migrated, 1)
        client.query_iterator.assert_called_once_with(
            collection_name="sage_memories",
            batch_size=1000,
            limit=-1,
            filter="",
            output_fields=["id", "content", "meta_data"],
        )
        upsert_mock.assert_called_once()
        flush_mock.assert_called_once()
        self.assertTrue(iterator.closed)

    def test_run_startup_migrations_saves_version_only_after_success(self) -> None:
        initial_conf = {"data_migration_version": 0}
        saved = {}

        def fake_load():
            return dict(initial_conf)

        def fake_save(conf):
            saved.update(conf)

        with patch("core.migrate.cfg.load", side_effect=fake_load), \
             patch("core.migrate.cfg.save", side_effect=fake_save), \
             patch("core.migrate.migrate_sqlite_to_milvus", return_value=2), \
             patch("core.migrate.migrate_legacy_milvus_memories", return_value=3), \
             patch("core.migrate.cleanup_legacy_vault_rows", return_value=4):
            result = migrate.run_startup_migrations()

        self.assertEqual(
            result,
            {
                "sqlite_to_milvus": 2,
                "legacy_milvus_reindexed": 3,
                "legacy_vault_rows_cleaned": 4,
            },
        )
        self.assertEqual(saved["data_migration_version"], 3)

    def test_run_startup_migrations_does_not_save_when_reindex_fails(self) -> None:
        with patch("core.migrate.cfg.load", return_value={"data_migration_version": 1}), \
             patch("core.migrate.cfg.save") as save_mock, \
             patch("core.migrate.migrate_legacy_milvus_memories", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                migrate.run_startup_migrations()

        save_mock.assert_not_called()

    def test_cleanup_legacy_vault_rows_replaces_old_row_and_deletes_legacy_id(self) -> None:
        iterator = _FakeIterator(
            [
                [{"id": "legacy-id", "content": "dados chamaelas\n[VAULT:abc]", "meta_data": {}}],
                [],
            ]
        )
        client = Mock()
        client.query_iterator.return_value = iterator
        db = Mock()
        db.collection = "sage_memories"
        db.client = client

        with patch("core.milvus_memory.get_milvus", return_value=db), \
             patch("core.milvus_memory.upsert_memory") as upsert_mock, \
             patch("core.milvus_memory.delete_by_id") as delete_mock, \
             patch("core.vault.extract_full_text", return_value="dados chamaelas\nsenha: 123456"), \
             patch("core.vault.sanitize_for_retrieval", return_value="dados chamaelas\nsenha: [PASSWORD]"), \
             patch("core.milvus_memory.memory_document_id", return_value="canonical-id"):
            cleaned = migrate.cleanup_legacy_vault_rows()

        self.assertEqual(cleaned, 1)
        upsert_mock.assert_called_once_with(
            memory_id="canonical-id",
            text="dados chamaelas\nsenha: [PASSWORD]",
            original_text="dados chamaelas\nsenha: 123456",
            meta_data={},
        )
        delete_mock.assert_called_once_with("legacy-id")
        self.assertTrue(iterator.closed)

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
