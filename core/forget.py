"""
Forget — tiered memory retention for Sage.

Free users: memories unused for 30 days are permanently deleted.
Pro users: configurable retention period with soft-delete (marked as forgotten).
           User must confirm permanent deletion via Settings UI.
"""

import logging
import time
from pathlib import Path

from core import config as cfg

logger = logging.getLogger("sage.forget")

_FORGOTTEN_PATH = Path.home() / ".sage" / "forgotten.json"


def _load_forgotten() -> dict:
    """Load the soft-delete registry: {memory_id: forgotten_at_timestamp}."""
    import json
    if _FORGOTTEN_PATH.exists():
        try:
            return json.loads(_FORGOTTEN_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"memories": {}}


def _save_forgotten(data: dict) -> None:
    import json
    _FORGOTTEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _FORGOTTEN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_forgotten() -> dict:
    return _load_forgotten()


def mark_forgotten_memories(memory_ids: list[str]) -> int:
    """Soft-delete: mark memories as forgotten (Pro only). Returns count marked."""
    data = _load_forgotten()
    now = int(time.time())
    count = 0
    for mid in memory_ids:
        if mid not in data["memories"]:
            data["memories"][mid] = now
            count += 1
    _save_forgotten(data)
    return count


def unmark_forgotten_memories(memory_ids: list[str]) -> int:
    """Restore soft-deleted memories. Returns count restored."""
    data = _load_forgotten()
    count = 0
    for mid in memory_ids:
        if mid in data["memories"]:
            del data["memories"][mid]
            count += 1
    _save_forgotten(data)
    return count


def permanently_delete_memories(memory_ids: list[str]) -> int:
    """Hard-delete memories from Milvus and remove from forgotten registry."""
    from core.milvus_memory import delete_by_id

    count = 0
    for mid in memory_ids:
        if delete_by_id(mid):
            count += 1
        else:
            logger.warning("Failed to delete memory %s", mid)

    data = _load_forgotten()
    for mid in memory_ids:
        data["memories"].pop(mid, None)
    _save_forgotten(data)
    return count


def run_cleanup() -> dict:
    """
    Run the forget cleanup based on user plan.

    Free: hard-delete memories with created_at older than retention days.
    Pro: soft-delete (mark as forgotten) memories past retention period.
         Already-forgotten items are NOT auto-purged — user confirms via UI.

    Returns: {"memories_deleted": N}
    """
    from core.milvus_memory import get_all, delete_by_id

    conf = cfg.load()
    plan = conf.get("user_plan", "free")
    retention_days = int(conf.get("forget_retention_days", 30) or 30)
    cutoff = int(time.time()) - (retention_days * 86400)

    result = {"memories_deleted": 0}

    memories = get_all()
    expired_ids = [
        m["id"] for m in memories
        if (m.get("meta_data", {}).get("created_at") or 0) < cutoff
    ]

    if not expired_ids:
        logger.info("Forget: no expired memories (cutoff=%s days)", retention_days)
        return result

    if plan == "pro":
        count = mark_forgotten_memories(expired_ids)
        result["memories_deleted"] = count
        logger.info("Forget (pro): marked %d memories as forgotten", count)
    else:
        for mid in expired_ids:
            if delete_by_id(mid):
                result["memories_deleted"] += 1
            else:
                logger.warning("Forget: failed to delete memory %s", mid)
        logger.info("Forget (free): deleted %d memories", result["memories_deleted"])

    if result["memories_deleted"] > 0:
        from core.agent import reset_agent
        reset_agent()

    return result
