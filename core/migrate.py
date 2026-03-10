"""
One-time migration: agno SQLite memories → Milvus vector store.

Called at startup. If sage.db has user memories, migrate them to Milvus
and then remove the old sage.db file.
"""

import logging
from pathlib import Path

logger = logging.getLogger("sage.migrate")

DB_PATH = Path.home() / ".sage" / "sage.db"
USER_ID = "sage_user"


def migrate_sqlite_to_milvus() -> int:
    """
    Migrate all user memories from agno SQLite to Milvus.
    Returns the number of memories migrated.
    Deletes sage.db after successful migration.
    """
    if not DB_PATH.exists():
        return 0

    try:
        from agno.db.sqlite import SqliteDb
        db = SqliteDb(db_file=str(DB_PATH))
        memories = db.get_user_memories(user_id=USER_ID) or []
    except Exception as e:
        logger.warning("Could not read agno SQLite: %s", e)
        return 0

    if not memories:
        # No memories to migrate — clean up the file
        _remove_db()
        return 0

    from core.milvus_memory import store
    migrated = 0

    for m in memories:
        try:
            text = str(m.memory) if m.memory else ""
            if not text.strip():
                continue
            store(text)
            migrated += 1
        except Exception as e:
            logger.warning("Failed to migrate memory %s: %s", m.memory_id, e)

    logger.info("Migrated %d/%d memories from SQLite to Milvus", migrated, len(memories))

    if migrated > 0:
        _remove_db()

    return migrated


def _remove_db() -> None:
    """Remove the old sage.db file after migration."""
    try:
        DB_PATH.unlink(missing_ok=True)
        logger.info("Removed old sage.db")
    except Exception as e:
        logger.warning("Could not remove sage.db: %s", e)
