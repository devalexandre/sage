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

    def test_show_onboarding_if_needed_skips_when_opted_out(self) -> None:
        tray = Mock()
        dialog_factory = Mock()
        save_conf = Mock()

        opened = app._show_onboarding_if_needed(
            tray,
            {"language": "pt-BR", "onboarding_opt_out": True},
            dialog_factory=dialog_factory,
            save_conf=save_conf,
        )

        self.assertIsNone(opened)
        tray._open_settings.assert_not_called()
        dialog_factory.assert_not_called()
        save_conf.assert_not_called()

    def test_show_onboarding_if_needed_shows_and_persists_opt_out(self) -> None:
        class _Signal:
            def __init__(self) -> None:
                self._callbacks = []

            def connect(self, callback):
                self._callbacks.append(callback)

            def emit(self) -> None:
                for callback in list(self._callbacks):
                    callback()

        class _Dialog:
            def __init__(self, language: str) -> None:
                self.language = language
                self.open_settings_requested = _Signal()
                self.completed = _Signal()
                self.shown = False
                self.anchor = None

            def show(self) -> None:
                self.shown = True

            def skip_future_onboarding(self) -> bool:
                return True

            def position_near(self, anchor) -> None:
                self.anchor = anchor

            def raise_(self) -> None:
                return None

            def activateWindow(self) -> None:
                return None

        tray = Mock()
        anchor = Mock()
        save_conf = Mock()

        dialog = app._show_onboarding_if_needed(
            tray,
            {"language": "en", "onboarding_opt_out": False},
            anchor=anchor,
            dialog_factory=_Dialog,
            save_conf=save_conf,
        )

        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.shown)
        self.assertIs(dialog.anchor, anchor)
        dialog.open_settings_requested.emit()
        tray._open_settings.assert_called_once()
        dialog.completed.emit()
        save_conf.assert_called_once()
        self.assertTrue(save_conf.call_args.args[0]["onboarding_opt_out"])

    def test_show_onboarding_if_needed_keeps_showing_when_checkbox_is_off(self) -> None:
        class _Signal:
            def __init__(self) -> None:
                self._callbacks = []

            def connect(self, callback):
                self._callbacks.append(callback)

            def emit(self) -> None:
                for callback in list(self._callbacks):
                    callback()

        class _Dialog:
            def __init__(self, language: str) -> None:
                self.open_settings_requested = _Signal()
                self.completed = _Signal()
                self.shown = False

            def show(self) -> None:
                self.shown = True

            def skip_future_onboarding(self) -> bool:
                return False

            def raise_(self) -> None:
                return None

            def activateWindow(self) -> None:
                return None

        tray = Mock()
        save_conf = Mock()

        dialog = app._show_onboarding_if_needed(
            tray,
            {"language": "pt-BR", "onboarding_opt_out": False},
            dialog_factory=_Dialog,
            save_conf=save_conf,
        )

        self.assertTrue(dialog.shown)
        dialog.completed.emit()
        tray._open_settings.assert_not_called()
        save_conf.assert_not_called()

    def test_show_startup_windows_opens_onboarding_and_account_together(self) -> None:
        tray = Mock()

        with patch("app._show_onboarding_if_needed", return_value=False) as onboarding_mock:
            opened = app._show_startup_windows(
                tray,
                {"language": "pt-BR", "onboarding_opt_out": False, "order_id": ""},
            )

        self.assertFalse(opened)
        onboarding_mock.assert_called_once()
        self.assertEqual(onboarding_mock.call_args.args[0], tray)
        self.assertEqual(
            onboarding_mock.call_args.args[1],
            {"language": "pt-BR", "onboarding_opt_out": False, "order_id": ""},
        )
        self.assertIs(onboarding_mock.call_args.kwargs["anchor"], tray._account)
        tray._account.toggle.assert_called_once()
        tray.showMessage.assert_not_called()

    def test_show_startup_windows_shows_ready_message_when_order_exists(self) -> None:
        tray = Mock()
        tray.icon.return_value = Mock()

        with patch("app._show_onboarding_if_needed", return_value=False) as onboarding_mock:
            opened = app._show_startup_windows(
                tray,
                {"language": "en", "onboarding_opt_out": True, "order_id": "ord-123"},
            )

        self.assertFalse(opened)
        onboarding_mock.assert_called_once()
        self.assertEqual(onboarding_mock.call_args.args[0], tray)
        self.assertEqual(
            onboarding_mock.call_args.args[1],
            {"language": "en", "onboarding_opt_out": True, "order_id": "ord-123"},
        )
        self.assertIs(onboarding_mock.call_args.kwargs["anchor"], tray._account)
        tray._account.toggle.assert_not_called()
        tray.showMessage.assert_called_once()


if __name__ == "__main__":
    unittest.main()
