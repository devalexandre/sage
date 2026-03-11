"""
Milvus-backed memory store for Sage.

Stores user memories as vector embeddings in Milvus (local file or remote).
Only semantically relevant memories are retrieved per query — no context blowup.
"""

import logging
import os
import time
from hashlib import md5
from pathlib import Path

from core import config as cfg

logger = logging.getLogger("sage.milvus_memory")

_milvus_db = None


def _resolve_uri(raw_uri: str) -> str:
    """Expand ~ and ensure parent directory exists for local file URIs."""
    if raw_uri.startswith("~"):
        raw_uri = str(Path(raw_uri).expanduser())
    if not raw_uri.startswith("http"):
        Path(raw_uri).parent.mkdir(parents=True, exist_ok=True)
    return raw_uri


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


def store(text: str) -> str:
    """Store a memory text in Milvus. Returns the document ID."""
    from agno.knowledge.document import Document

    db = get_milvus()
    doc_id = md5(text.encode()).hexdigest()
    content_hash = md5(f"memory:{doc_id}".encode()).hexdigest()
    now = int(time.time())

    doc = Document(
        content=text,
        id=doc_id,
        name=f"memory_{doc_id[:8]}",
        meta_data={"type": "memory", "created_at": now, "updated_at": now},
    )

    db.insert(content_hash=content_hash, documents=[doc])
    logger.info("Stored memory %s (%d chars)", doc_id[:8], len(text))
    return doc_id


def search(query: str, limit: int = 5, min_score: float = 0.5) -> list[dict]:
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
                "meta_data": hit["entity"].get("meta_data", {}),
                "score": score,
            })

    logger.info("Milvus: %d/%d results above threshold %.2f",
                len(filtered), len(raw_results[0]), min_score)
    return filtered


def get_all(limit: int = 1000) -> list[dict]:
    """Return all stored memories (for UI display / management)."""
    db = get_milvus()
    try:
        results = db.client.query(
            collection_name=db.collection,
            filter="",
            output_fields=["id", "content", "meta_data"],
            limit=limit,
        )
        return [
            {
                "id": r.get("id", ""),
                "content": r.get("content", ""),
                "meta_data": r.get("meta_data", {}),
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
