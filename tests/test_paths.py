import importlib
import json


def test_windows_data_dir_migrates_legacy_config(monkeypatch, tmp_path):
    legacy_home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    legacy_dir = legacy_home / ".sage"
    new_dir = appdata / "Sage"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "config.json").write_text(
        json.dumps({"openai_api_key": "sk-test", "auth_token": "token-123"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setattr("pathlib.Path.home", lambda: legacy_home)

    import core.paths
    import core.config

    importlib.reload(core.paths)
    config = importlib.reload(core.config)

    conf = config.load()

    assert conf["openai_api_key"] == "sk-test"
    assert conf["auth_token"] == "token-123"
    assert (new_dir / "config.json").exists()
