"""
Startup data migrations for local Sage memory storage.

Current migrations:
1. Legacy Agno SQLite memories from sage.db -> SQLite memory store
2. Legacy Milvus file rows -> SQLite memory store
3. Reserved compatibility step
4. Qdrant-backed memories -> SQLite memory store
"""

import logging
from pathlib import Path

from agno.db.sqlite import SqliteDb

from core import config as cfg
from core.paths import DATA_DIR

logger = logging.getLogger("sage.migrate")

LEGACY_DB_PATH = DATA_DIR / "sage.db"
USER_ID = "sage_user"
LATEST_DATA_MIGRATION_VERSION = 4


def run_startup_migrations() -> dict[str, int]:
    """Run pending local data migrations once per installation."""
    conf = cfg.load()
    current_version = int(conf.get("data_migration_version", 0) or 0)
    summary = {
        "legacy_sqlite_imported": 0,
        "legacy_milvus_imported": 0,
        "qdrant_to_sqlite": 0,
    }

    if current_version < 1:
        summary["legacy_sqlite_imported"] = migrate_legacy_sqlite_memories()
        current_version = 1

    if current_version < 2:
        summary["legacy_milvus_imported"] = migrate_legacy_milvus_memories()
        current_version = 2

    if current_version < 3:
        current_version = 3

    if current_version < 4:
        summary["qdrant_to_sqlite"] = migrate_qdrant_memories()
        current_version = 4

    if current_version != int(conf.get("data_migration_version", 0) or 0):
        conf = cfg.load()
        conf["data_migration_version"] = current_version
        cfg.save(conf)

    return summary


def migrate_legacy_sqlite_memories() -> int:
    """
    Migrate user memories from the old Agno SQLite database at sage.db.
    Returns the number of imported memories.
    """
    if not LEGACY_DB_PATH.exists():
        return 0

    db = SqliteDb(db_file=str(LEGACY_DB_PATH))
    memories = db.get_user_memories(user_id=USER_ID) or []

    if not memories:
        _remove_legacy_db()
        return 0

    from core.sqlite_memory import store
    from core.vault import sanitize_for_retrieval

    imported = 0
    for memory in memories:
        try:
            text = str(memory.memory or "").strip()
            if not text:
                continue
            store(sanitize_for_retrieval(text), original_text=text)
            imported += 1
        except Exception as exc:
            logger.warning("Failed to migrate legacy SQLite memory %s: %s", getattr(memory, "memory_id", ""), exc)

    if imported or not memories:
        _remove_legacy_db()

    logger.info("Imported %d/%d legacy SQLite memories", imported, len(memories))
    return imported


def migrate_legacy_milvus_memories() -> int:
    from core.sqlite_memory import store
    from core.vault import extract_full_text, sanitize_for_retrieval

    imported = 0
    for row in _iter_legacy_milvus_rows():
        try:
            memory = {
                "id": row.get("id", ""),
                "content": row.get("content", ""),
                "meta_data": row.get("meta_data", {}),
            }
            full_text = extract_full_text(memory).strip()
            if not full_text:
                continue
            store(sanitize_for_retrieval(full_text), original_text=full_text)
            imported += 1
        except Exception as exc:
            logger.warning("Failed to import legacy Milvus memory %s: %s", row.get("id", ""), exc)

    if imported:
        logger.info("Imported %d legacy Milvus memories into SQLite", imported)
    return imported


def migrate_qdrant_memories() -> int:
    from core.sqlite_memory import store
    from core.vault import extract_full_text, sanitize_for_retrieval

    imported = 0
    for memory in _iter_qdrant_memories():
        try:
            full_text = extract_full_text(memory).strip()
            if not full_text:
                continue
            store(sanitize_for_retrieval(full_text), original_text=full_text)
            imported += 1
        except Exception as exc:
            logger.warning("Failed to import Qdrant memory %s: %s", memory.get("id", ""), exc)

    if imported:
        logger.info("Imported %d Qdrant memories into SQLite", imported)
    return imported


def _remove_legacy_db() -> None:
    try:
        LEGACY_DB_PATH.unlink(missing_ok=True)
        logger.info("Removed legacy sage.db")
    except Exception as exc:
        logger.warning("Could not remove legacy sage.db: %s", exc)


def _iter_qdrant_memories() -> list[dict]:
    try:
        from core.qdrant_memory import get_all_raw
    except Exception as exc:
        logger.info("Skipping Qdrant memory migration: %s", exc)
        return []

    try:
        return get_all_raw(limit=100_000)
    except Exception as exc:
        logger.info("Skipping Qdrant memory migration: %s", exc)
        return []


def _iter_legacy_milvus_rows() -> list[dict]:
    conf = cfg.load()
    legacy_uri = str(conf.get("milvus_uri", DATA_DIR / "milvus.db"))
    if legacy_uri.startswith("~"):
        legacy_uri = str(Path(legacy_uri).expanduser())
    if legacy_uri.startswith("http"):
        return []

    legacy_path = Path(legacy_uri)
    if not legacy_path.exists():
        return []

    try:
        from pymilvus import MilvusClient
    except Exception:
        logger.info("Skipping legacy Milvus migration because pymilvus is unavailable")
        return []

    try:
        client = MilvusClient(uri=str(legacy_path), token=conf.get("milvus_token", "").strip() or "")
        iterator = client.query_iterator(
            collection_name=conf.get("milvus_collection", "sage_memories"),
            batch_size=1000,
            limit=-1,
            filter="",
            output_fields=["id", "content", "meta_data"],
        )
    except Exception as exc:
        logger.info("Skipping legacy Milvus migration: %s", exc)
        return []

    rows = []
    try:
        while True:
            batch = iterator.next()
            if not batch:
                break
            rows.extend(batch)
    finally:
        try:
            iterator.close()
        except Exception:
            pass

    return rows
