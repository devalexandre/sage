import os
import shutil
from pathlib import Path


APP_NAME = "Sage"
LEGACY_DATA_DIR = Path.home() / ".sage"


def _resolve_data_dir() -> Path:
    if os.name != "nt":
        return LEGACY_DATA_DIR

    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if not base:
        return LEGACY_DATA_DIR
    return Path(base) / APP_NAME


DATA_DIR = _resolve_data_dir()


def ensure_data_dir() -> Path:
    _migrate_legacy_data_dir()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def _migrate_legacy_data_dir() -> None:
    if DATA_DIR == LEGACY_DATA_DIR or not LEGACY_DATA_DIR.exists():
        return

    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)

    if not DATA_DIR.exists():
        shutil.copytree(LEGACY_DATA_DIR, DATA_DIR)
        return

    for source in LEGACY_DATA_DIR.iterdir():
        target = DATA_DIR / source.name
        if target.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
