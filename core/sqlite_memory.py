import json
import logging
import re
import time
import unicodedata
from hashlib import md5
from typing import Any

from agno.db.schemas.memory import UserMemory
from agno.db.sqlite import SqliteDb

from core.paths import DATA_DIR
from core.vault import encrypt_text as encrypt_vault_text

logger = logging.getLogger("sage.sqlite_memory")

MEMORY_DB_PATH = DATA_DIR / "memory.db"
MEMORY_TABLE = "sage_user_memories"
SESSION_TABLE = "sage_agent_sessions"
USER_ID = "sage_user"

_db: SqliteDb | None = None

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
    "em", "para", "por", "com", "sem", "e", "ou",
    "meu", "minha", "meus", "minhas", "seu", "sua", "seus", "suas",
    "qual", "quais", "que",
}


def memory_document_id(text: str) -> str:
    return md5(text.encode("utf-8")).hexdigest()


def _normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _query_tokens(query: str) -> list[str]:
    normalized = _normalize_for_match(query)
    return [
        token for token in _TOKEN_RE.findall(normalized)
        if len(token) >= 3 and token not in _STOPWORDS
    ]


def _preview_text(content: str) -> str:
    for line in content.splitlines():
        line = line.strip()
        if line:
            return line
    return content.strip()


def _select_lexical_matches(rows: list[dict], query: str, limit: int) -> list[dict]:
    tokens = _query_tokens(query)
    if not tokens:
        return []

    ranked: list[dict] = []
    for row in rows:
        content = row.get("content", "")
        preview = _preview_text(content)
        haystack = _normalize_for_match(preview)
        matched = [token for token in tokens if token in haystack]
        if not matched:
            continue

        score = len(matched) / len(tokens)
        if " ".join(tokens) in haystack:
            score += 0.25

        ranked.append({
            "id": row.get("id", ""),
            "content": content,
            "meta_data": row.get("meta_data", {}),
            "score": min(score, 1.0),
        })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def _get_db() -> SqliteDb:
    global _db
    if _db is None:
        _db = SqliteDb(
            db_file=str(MEMORY_DB_PATH),
            memory_table=MEMORY_TABLE,
            session_table=SESSION_TABLE,
        )
    return _db


def _normalize_meta_data(meta_data: Any) -> dict[str, Any]:
    if isinstance(meta_data, dict):
        return dict(meta_data)
    if isinstance(meta_data, str):
        try:
            parsed = json.loads(meta_data)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _memory_to_dict(memory: UserMemory) -> dict[str, Any]:
    meta = _normalize_meta_data(memory.feedback)
    meta.setdefault("type", "memory")
    if memory.created_at:
        meta.setdefault("created_at", int(memory.created_at))
    if memory.updated_at:
        meta["updated_at"] = int(memory.updated_at)
    if memory.input:
        meta["vault_ciphertext"] = memory.input

    return {
        "id": memory.memory_id or "",
        "content": memory.memory or "",
        "meta_data": meta,
    }


def _build_user_memory(
    memory_id: str,
    text: str,
    *,
    original_text: str,
    meta_data: dict[str, Any] | None = None,
) -> UserMemory:
    now = int(time.time())
    normalized_meta = _normalize_meta_data(meta_data)
    normalized_meta.setdefault("type", "memory")
    normalized_meta.setdefault("created_at", now)
    normalized_meta["updated_at"] = now
    vault_ciphertext = normalized_meta.pop("vault_ciphertext", "") or encrypt_vault_text(original_text)

    return UserMemory(
        memory=text,
        memory_id=memory_id,
        user_id=USER_ID,
        input=vault_ciphertext,
        feedback=json.dumps(normalized_meta, ensure_ascii=True),
        created_at=int(normalized_meta["created_at"]),
        updated_at=int(normalized_meta["updated_at"]),
    )


def reset() -> None:
    global _db
    _db = None


def flush() -> None:
    """Writes are synchronous for the local SQLite memory store."""


def store(text: str, *, original_text: str | None = None) -> str:
    source_text = original_text or text
    doc_id = memory_document_id(source_text)
    user_memory = _build_user_memory(doc_id, text, original_text=source_text)
    _get_db().upsert_user_memory(user_memory)
    logger.info("Stored memory %s (%d chars)", doc_id[:8], len(text))
    return doc_id


def upsert_memory(memory_id: str, text: str, *, original_text: str, meta_data: dict | None = None) -> str:
    user_memory = _build_user_memory(
        memory_id,
        text,
        original_text=original_text,
        meta_data=meta_data,
    )
    _get_db().upsert_user_memory(user_memory)
    logger.info("Upserted memory %s (%d chars)", memory_id[:8], len(text))
    return memory_id


def get_all(limit: int = 1000) -> list[dict]:
    try:
        memories = _get_db().get_user_memories(user_id=USER_ID, limit=limit) or []
        return [_memory_to_dict(memory) for memory in memories]
    except Exception:
        logger.exception("Failed to list all memories")
        return []


def get_all_raw(limit: int = 1000) -> list[dict]:
    return get_all(limit=limit)


def search(query: str, limit: int = 5, min_score: float = 0.35) -> list[dict]:
    try:
        rows = get_all(limit=100_000)
        matches = _select_lexical_matches(rows, query, limit=limit)
        return [match for match in matches if float(match.get("score", 0.0) or 0.0) >= min_score]
    except Exception:
        logger.exception("Failed to search memories")
        return []


def delete_by_id(memory_id: str) -> bool:
    try:
        _get_db().delete_user_memory(memory_id, user_id=USER_ID)
        return True
    except Exception as exc:
        logger.warning("Failed to delete memory %s: %s", memory_id, exc)
        return False


def count() -> int:
    return len(get_all(limit=100_000))


def export_memory_snapshot() -> dict[str, Any]:
    return {
        "format": "agno_sqlite_memory_v1",
        "memories": get_all_raw(limit=100_000),
    }


def import_memory_snapshot(snapshot: dict[str, Any]) -> None:
    reset_memory_store()
    for memory in snapshot.get("memories", []):
        meta = memory.get("meta_data", {}) or {}
        original_text = ""
        if isinstance(meta, dict):
            original_text = meta.get("vault_ciphertext", "")
        upsert_memory(
            memory_id=str(memory.get("id", "")),
            text=str(memory.get("content", "")),
            original_text=original_text or str(memory.get("content", "")),
            meta_data=meta,
        )


def reset_memory_store() -> None:
    try:
        _get_db().clear_memories()
    finally:
        reset()
