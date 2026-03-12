"""
Milvus-backed memory store for Sage.

Stores user memories as vector embeddings in Milvus (local file or remote).
Only semantically relevant memories are retrieved per query — no context blowup.
"""

import logging
import json
import os
import sys
import time
import re
import unicodedata
from hashlib import md5
from importlib import resources
from pathlib import Path

from core import config as cfg
from core.vault import encrypt_text as encrypt_vault_text

logger = logging.getLogger("sage.milvus_memory")

_milvus_db = None
_QUERY_LIMIT_MAX = 16_384

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
    "em", "para", "por", "com", "sem", "e", "ou",
    "meu", "minha", "meus", "minhas", "seu", "sua", "seus", "suas",
    "qual", "quais", "que",
}


def memory_document_id(text: str) -> str:
    return md5(text.encode()).hexdigest()


def _resolve_uri(raw_uri: str) -> str:
    """Expand ~ and ensure parent directory exists for local file URIs."""
    if raw_uri.startswith("~"):
        raw_uri = str(Path(raw_uri).expanduser())
    if not raw_uri.startswith("http"):
        Path(raw_uri).parent.mkdir(parents=True, exist_ok=True)
    return raw_uri


def _configure_milvus_lite_bin_path() -> None:
    """Point milvus-lite at its bundled native binaries when running packaged builds."""
    if os.environ.get("BIN_PATH"):
        return

    candidates: list[Path] = []
    executable_names = ("milvus", "milvus.exe")

    try:
        resource_dir = resources.files("milvus_lite").joinpath("lib")
        candidates.append(Path(str(resource_dir)))
    except Exception:
        pass

    try:
        import milvus_lite

        candidates.append(Path(milvus_lite.__file__).resolve().parent / "lib")
    except Exception:
        pass

    exe_dir = Path(sys.argv[0]).resolve().parent
    candidates.append(exe_dir / "milvus_lite" / "lib")
    candidates.append(exe_dir / "lib" / "milvus_lite" / "lib")
    candidates.append(exe_dir.parent / "Resources" / "milvus_lite" / "lib")
    candidates.append(exe_dir.parent / "Frameworks" / "milvus_lite" / "lib")
    candidates.append(Path(sys.executable).resolve().parent / "milvus_lite" / "lib")

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if any((candidate / name).exists() for name in executable_names):
            os.environ["BIN_PATH"] = str(candidate)
            logger.info("Configured milvus-lite BIN_PATH=%s", candidate)
            return

    logger.info("milvus-lite BIN_PATH not auto-detected; tried=%s", ", ".join(str(path) for path in seen))


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


def _normalize_meta_data(meta_data) -> dict:
    if isinstance(meta_data, dict):
        return dict(meta_data)
    if isinstance(meta_data, str):
        try:
            parsed = json.loads(meta_data)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _query_rows(db, *, limit: int, output_fields: list[str]) -> list[dict]:
    if limit <= 0:
        return []

    if limit <= _QUERY_LIMIT_MAX:
        return db.client.query(
            collection_name=db.collection,
            filter="",
            output_fields=output_fields,
            limit=limit,
        )

    iterator = db.client.query_iterator(
        collection_name=db.collection,
        batch_size=min(1000, _QUERY_LIMIT_MAX),
        limit=limit,
        filter="",
        output_fields=output_fields,
    )
    rows: list[dict] = []
    try:
        while len(rows) < limit:
            batch = iterator.next()
            if not batch:
                break
            rows.extend(batch)
        return rows[:limit]
    finally:
        try:
            iterator.close()
        except Exception as e:
            logger.warning("Failed to close Milvus query iterator: %s", e)


def _build_embedder(conf: dict):
    provider = conf.get("embed_provider", "openai")
    model = conf.get("embed_model", "text-embedding-3-small")
    dims = int(conf.get("embed_dimensions", 1536) or 1536)

    if provider == "ollama":
        from agno.knowledge.embedder.ollama import OllamaEmbedder
        return OllamaEmbedder(
            id=model or "openhermes",
            dimensions=dims,
            host=conf.get("ollama_host") or None,
        )

    from agno.knowledge.embedder.openai import OpenAIEmbedder
    api_key = conf.get("openai_api_key", "").strip()
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    return OpenAIEmbedder(id=model, dimensions=dims)


def get_milvus():
    """Return the singleton Milvus vector DB instance for memories."""
    global _milvus_db
    if _milvus_db is not None:
        return _milvus_db

    conf = cfg.load()
    _configure_milvus_lite_bin_path()
    uri = _resolve_uri(conf.get("milvus_uri", "~/.sage/milvus.db"))
    token = conf.get("milvus_token", "").strip() or None
    collection = conf.get("milvus_collection", "sage_memories")

    from agno.vectordb.milvus import Milvus

    embedder = _build_embedder(conf)
    _milvus_db = Milvus(
        collection=collection,
        uri=uri,
        token=token,
        embedder=embedder,
    )

    if not _milvus_db.exists():
        _milvus_db.create()
        logger.info("Created Milvus collection: %s", collection)

    logger.info("Milvus memory store ready (uri=%s, collection=%s)", uri, collection)
    return _milvus_db


def reset():
    """Release and discard the cached Milvus instance."""
    global _milvus_db
    if _milvus_db is not None:
        try:
            _milvus_db.client.release_collection(_milvus_db.collection)
        except Exception:
            pass
        try:
            _milvus_db.client.close()
        except Exception:
            pass
    _milvus_db = None


def flush() -> None:
    """Force pending local Milvus changes to disk before backup/export."""
    db = get_milvus()
    try:
        db.client.flush(collection_name=db.collection)
    except Exception as e:
        logger.warning("Failed to flush Milvus collection %s: %s", db.collection, e)


def store(text: str, *, original_text: str | None = None) -> str:
    """Store a memory text in Milvus. Returns the document ID."""
    from agno.knowledge.document import Document

    db = get_milvus()
    source_text = original_text or text
    doc_id = memory_document_id(source_text)
    content_hash = md5(f"memory:{doc_id}".encode()).hexdigest()
    now = int(time.time())

    doc = Document(
        content=text,
        id=doc_id,
        name=f"memory_{doc_id[:8]}",
        meta_data={
            "type": "memory",
            "created_at": now,
            "updated_at": now,
            "vault_ciphertext": encrypt_vault_text(source_text),
        },
    )

    db.insert(content_hash=content_hash, documents=[doc])
    logger.info("Stored memory %s (%d chars)", doc_id[:8], len(text))
    return doc_id


def upsert_memory(memory_id: str, text: str, *, original_text: str, meta_data: dict | None = None) -> str:
    """Upsert an existing memory while preserving its identifier."""
    db = get_milvus()
    now = int(time.time())
    normalized_meta = _normalize_meta_data(meta_data)
    normalized_meta.setdefault("type", "memory")
    normalized_meta.setdefault("created_at", now)
    normalized_meta["updated_at"] = now
    normalized_meta["vault_ciphertext"] = encrypt_vault_text(original_text)
    content_hash = md5(f"memory:{memory_id}".encode()).hexdigest()
    embedding = db.embedder.get_embedding(text)
    if embedding is None:
        raise RuntimeError(f"Failed to build embedding for memory {memory_id}")

    db.client.upsert(
        collection_name=db.collection,
        data={
            "id": memory_id,
            "vector": embedding,
            "name": f"memory_{memory_id[:8]}",
            "content_id": "",
            "meta_data": normalized_meta,
            "content": text,
            "usage": {},
            "content_hash": content_hash,
        },
    )
    logger.info("Upserted memory %s (%d chars)", memory_id[:8], len(text))
    return memory_id


def search(query: str, limit: int = 5, min_score: float = 0.35) -> list[dict]:
    """
    Search memories by semantic similarity.
    Only returns results with score >= min_score.
    Returns list of {id, content, meta_data, score}.
    """
    db = get_milvus()

    # Use raw client to get distance scores
    query_embedding = db.embedder.get_embedding(query)
    if query_embedding is None:
        logger.warning("Failed to get embedding for query")
        return []

    raw_results = db.client.search(
        collection_name=db.collection,
        data=[query_embedding],
        output_fields=["id", "content", "meta_data"],
        limit=limit,
    )

    filtered = []
    for hit in raw_results[0]:
        dist = hit["distance"]
        # Milvus COSINE: distance in [0, 2], similarity = 1 - distance/2
        # But pymilvus may return similarity directly (higher = better)
        # Log raw distance to understand the metric
        score = dist if dist <= 1.0 else 1.0 - (dist - 1.0)
        logger.info("Memory hit distance=%.4f score=%.4f id=%s content=%.40s",
                     dist, score, hit["id"],
                     hit["entity"].get("content", "")[:40])
        if score >= min_score:
            filtered.append({
                "id": hit["id"],
                "content": hit["entity"].get("content", ""),
                "meta_data": _normalize_meta_data(hit["entity"].get("meta_data", {})),
                "score": score,
            })

    logger.info("Milvus: %d/%d results above threshold %.2f",
                len(filtered), len(raw_results[0]), min_score)

    if filtered:
        return filtered

    try:
        rows = _query_rows(
            db,
            limit=max(limit * 20, 100),
            output_fields=["id", "content", "meta_data"],
        )
    except Exception as e:
        logger.warning("Milvus lexical fallback failed: %s", e)
        return filtered

    fallback = _select_lexical_matches(rows, query, limit=limit)
    if fallback:
        logger.info("Milvus lexical fallback recovered %d result(s) for query=%r", len(fallback), query)
    return fallback


def get_all(limit: int = 1000) -> list[dict]:
    """Return all stored memories (for UI display / management)."""
    db = get_milvus()
    try:
        results = _query_rows(
            db,
            limit=limit,
            output_fields=["id", "content", "meta_data"],
        )
        return [
            {
                "id": r.get("id", ""),
                "content": r.get("content", ""),
                "meta_data": _normalize_meta_data(r.get("meta_data", {})),
            }
            for r in results
        ]
    except Exception as e:
        logger.warning("Failed to list all memories: %s", e)
        return []


def delete_by_id(memory_id: str) -> bool:
    """Delete a single memory by its ID."""
    db = get_milvus()
    try:
        return db.delete_by_id(id=memory_id)
    except Exception as e:
        logger.warning("Failed to delete memory %s: %s", memory_id, e)
        return False


def count() -> int:
    """Return total number of stored memories."""
    try:
        return len(get_all())
    except Exception:
        return 0
