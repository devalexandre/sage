"""
Startup data migrations for local Sage storage.

Current migrations:
1. Legacy agno SQLite memories -> Milvus
2. Legacy Milvus memories -> retrieval-safe redacted content + encrypted full text
"""

import logging
from pathlib import Path
from typing import Iterator

from core import config as cfg

logger = logging.getLogger("sage.migrate")

DB_PATH = Path.home() / ".sage" / "sage.db"
USER_ID = "sage_user"
LATEST_DATA_MIGRATION_VERSION = 3


def run_startup_migrations() -> dict[str, int]:
    """Run pending local data migrations once per installation."""
    conf = cfg.load()
    current_version = int(conf.get("data_migration_version", 0) or 0)
    summary = {
        "sqlite_to_milvus": 0,
        "legacy_milvus_reindexed": 0,
        "legacy_vault_rows_cleaned": 0,
    }

    if current_version < 1:
        summary["sqlite_to_milvus"] = migrate_sqlite_to_milvus()
        current_version = 1

    if current_version < 2:
        summary["legacy_milvus_reindexed"] = migrate_legacy_milvus_memories()
        current_version = 2

    if current_version < 3:
        summary["legacy_vault_rows_cleaned"] = cleanup_legacy_vault_rows()
        current_version = 3

    if current_version != int(conf.get("data_migration_version", 0) or 0):
        conf = cfg.load()
        conf["data_migration_version"] = current_version
        cfg.save(conf)

    return summary


def migrate_sqlite_to_milvus() -> int:
    """
    Migrate all user memories from agno SQLite to Milvus.
    Returns the number of memories migrated.
    Deletes sage.db after successful migration.
    """
    if not DB_PATH.exists():
        return 0

    from agno.db.sqlite import SqliteDb

    db = SqliteDb(db_file=str(DB_PATH))
    memories = db.get_user_memories(user_id=USER_ID) or []

    if not memories:
        _remove_db()
        return 0

    from core.milvus_memory import store
    from core.vault import sanitize_for_retrieval

    migrated = 0
    for m in memories:
        try:
            text = str(m.memory) if m.memory else ""
            if not text.strip():
                continue
            store(sanitize_for_retrieval(text), original_text=text)
            migrated += 1
        except Exception as e:
            logger.warning("Failed to migrate memory %s: %s", getattr(m, "memory_id", ""), e)

    logger.info("Migrated %d/%d memories from SQLite to Milvus", migrated, len(memories))

    if migrated > 0:
        _remove_db()

    return migrated


def migrate_legacy_milvus_memories() -> int:
    """Reindex legacy Milvus memories to store encrypted full text plus redacted retrieval text."""
    from core.milvus_memory import _normalize_meta_data, flush, get_milvus, upsert_memory
    from core.vault import extract_full_text, sanitize_for_retrieval

    db = get_milvus()
    migrated = 0
    for row in _iter_legacy_milvus_rows(db):
        memory = {
            "id": row.get("id", ""),
            "content": row.get("content", ""),
            "meta_data": _normalize_meta_data(row.get("meta_data", {})),
        }
        try:
            meta = memory.get("meta_data", {}) or {}
            full_text = extract_full_text(memory).strip()
            if not full_text:
                continue

            retrieval_text = sanitize_for_retrieval(full_text)
            has_ciphertext = bool(meta.get("vault_ciphertext"))
            content_matches = memory.get("content", "") == retrieval_text
            if has_ciphertext and content_matches:
                continue

            upsert_memory(
                memory_id=memory.get("id", ""),
                text=retrieval_text,
                original_text=full_text,
                meta_data=meta,
            )
            migrated += 1
        except Exception as e:
            logger.warning("Failed to reindex legacy Milvus memory %s: %s", memory.get("id", ""), e)

    if migrated:
        flush()
    logger.info("Reindexed %d legacy Milvus memories", migrated)
    return migrated


def _iter_legacy_milvus_rows(db, batch_size: int = 1000) -> Iterator[dict]:
    iterator = db.client.query_iterator(
        collection_name=db.collection,
        batch_size=batch_size,
        limit=-1,
        filter="",
        output_fields=["id", "content", "meta_data"],
    )
    try:
        while True:
            batch = iterator.next()
            if not batch:
                break
            for row in batch:
                yield row
    finally:
        try:
            iterator.close()
        except Exception as e:
            logger.warning("Failed to close Milvus query iterator: %s", e)


def cleanup_legacy_vault_rows() -> int:
    """Remove legacy Milvus rows that still store [VAULT:...] content or missing ciphertext."""
    from core.milvus_memory import (
        _normalize_meta_data,
        delete_by_id,
        get_milvus,
        memory_document_id,
        upsert_memory,
    )
    from core.vault import extract_full_text, sanitize_for_retrieval

    db = get_milvus()
    cleaned = 0

    for row in _iter_legacy_milvus_rows(db):
        memory = {
            "id": row.get("id", ""),
            "content": row.get("content", ""),
            "meta_data": _normalize_meta_data(row.get("meta_data", {})),
        }
        meta = memory["meta_data"]
        content = memory["content"]
        row_id = memory["id"]

        try:
            full_text = extract_full_text(memory).strip()
            if not full_text:
                continue

            target_id = memory_document_id(full_text)
            retrieval_text = sanitize_for_retrieval(full_text)
            has_ciphertext = bool(meta.get("vault_ciphertext"))
            has_legacy_tokens = "[VAULT:" in content
            is_current = has_ciphertext and content == retrieval_text and row_id == target_id
            if is_current:
                continue

            upsert_memory(
                memory_id=target_id,
                text=retrieval_text,
                original_text=full_text,
                meta_data=meta,
            )

            if row_id != target_id or has_legacy_tokens or not has_ciphertext:
                delete_by_id(row_id)
            cleaned += 1
        except Exception as e:
            logger.warning("Failed to clean legacy Milvus row %s: %s", row_id, e)

    logger.info("Cleaned %d legacy Milvus rows", cleaned)
    return cleaned


def _remove_db() -> None:
    """Remove the old sage.db file after migration."""
    try:
        DB_PATH.unlink(missing_ok=True)
        logger.info("Removed old sage.db")
    except Exception as e:
        logger.warning("Could not remove sage.db: %s", e)
