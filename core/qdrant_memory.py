"""
Qdrant-backed memory store for Sage.

Stores user memories as vector embeddings in a dedicated Qdrant collection.
Only semantically relevant memories are retrieved per query.
"""

import json
import logging
import os
import re
import time
import unicodedata
from hashlib import md5
from typing import Any

from qdrant_client.http import models

from core import config as cfg
from core.qdrant_common import (
    QdrantConfigurationError,
    build_qdrant_client,
    ensure_qdrant_configured,
)
from core.vault import encrypt_text as encrypt_vault_text

logger = logging.getLogger("sage.qdrant_memory")

_client = None
_client_key: tuple[str, str] | None = None
_embedder = None
_embedder_key: tuple[str, str, int, str] | None = None
_SCROLL_BATCH_SIZE = 256
_DEFAULT_MEMORY_COLLECTION = "sage_memory_vault"
_LEGACY_COLLECTION_NAMES = ("sage_memories",)

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


def _get_embedder(conf: dict):
    global _embedder, _embedder_key
    key = (
        conf.get("embed_provider", "openai"),
        conf.get("embed_model", "text-embedding-3-small"),
        int(conf.get("embed_dimensions", 1536) or 1536),
        conf.get("openai_api_key", "").strip(),
    )
    if _embedder is None or _embedder_key != key:
        _embedder = _build_embedder(conf)
        _embedder_key = key
    return _embedder


def _collection_name(conf: dict) -> str:
    return conf.get("qdrant_memory_collection", _DEFAULT_MEMORY_COLLECTION).strip() or _DEFAULT_MEMORY_COLLECTION


def _scroll_collection_records(client, collection: str, *, with_vectors: bool, limit: int | None = None) -> list:
    records = []
    offset = None
    remaining = limit

    while remaining is None or remaining > 0:
        batch_limit = _SCROLL_BATCH_SIZE if remaining is None else min(_SCROLL_BATCH_SIZE, remaining)
        batch, offset = client.scroll(
            collection_name=collection,
            limit=batch_limit,
            with_payload=True,
            with_vectors=with_vectors,
            offset=offset,
        )
        records.extend(batch)
        if offset is None or not batch:
            break
        if remaining is not None:
            remaining -= len(batch)

    return records


def _migrate_legacy_collection_if_needed(client, target_collection: str, conf: dict) -> bool:
    if client.collection_exists(target_collection):
        return False

    for legacy_name in _LEGACY_COLLECTION_NAMES:
        if legacy_name == target_collection or not client.collection_exists(legacy_name):
            continue

        dims = int(conf.get("embed_dimensions", 1536) or 1536)
        client.create_collection(
            collection_name=target_collection,
            vectors_config=models.VectorParams(
                size=dims,
                distance=models.Distance.COSINE,
            ),
        )
        legacy_records = _scroll_collection_records(client, legacy_name, with_vectors=True)
        if legacy_records:
            points = [
                models.PointStruct(
                    id=str(record.id),
                    vector=record.vector,
                    payload=record.payload or {},
                )
                for record in legacy_records
            ]
            client.upsert(collection_name=target_collection, points=points, wait=True)
        logger.info(
            "Migrated legacy Qdrant memory collection from %s to %s (%d points)",
            legacy_name,
            target_collection,
            len(legacy_records),
        )
        return True

    return False


def _get_client(conf: dict | None = None, *, feature: str = "Memory") -> tuple[Any, dict]:
    global _client, _client_key

    if conf is None:
        conf = cfg.load()

    url = ensure_qdrant_configured(conf, feature=feature)
    api_key = conf.get("qdrant_api_key", "").strip()
    key = (url, api_key)
    if _client is None or _client_key != key:
        _client = build_qdrant_client(conf, feature=feature)
        _client_key = key
    return _client, conf


def _ensure_collection(conf: dict | None = None, *, feature: str = "Memory") -> tuple[Any, str, dict]:
    client, conf = _get_client(conf, feature=feature)
    collection = _collection_name(conf)
    try:
        migrated = _migrate_legacy_collection_if_needed(client, collection, conf)
        if not migrated and not client.collection_exists(collection):
            dims = int(conf.get("embed_dimensions", 1536) or 1536)
            client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=dims,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant memory collection: %s", collection)
    except Exception as exc:
        raise QdrantConfigurationError(
            "Memory storage could not reach Qdrant. Start the Qdrant Docker container "
            "or configure a reachable Qdrant URL in Settings > Documents."
        ) from exc
    return client, collection, conf


def reset() -> None:
    global _client, _client_key, _embedder, _embedder_key
    if _client is not None:
        close = getattr(_client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    _client = None
    _client_key = None
    _embedder = None
    _embedder_key = None


def flush() -> None:
    """Qdrant writes synchronously for our use case; retained for compatibility."""


def store(text: str, *, original_text: str | None = None) -> str:
    client, collection, conf = _ensure_collection(feature="Memory storage")
    embedder = _get_embedder(conf)
    source_text = original_text or text
    doc_id = memory_document_id(source_text)
    now = int(time.time())
    embedding = embedder.get_embedding(text)
    if embedding is None:
        raise RuntimeError(f"Failed to build embedding for memory {doc_id}")

    client.upsert(
        collection_name=collection,
        points=[
            models.PointStruct(
                id=doc_id,
                vector=embedding,
                payload={
                    "content": text,
                    "meta_data": {
                        "type": "memory",
                        "created_at": now,
                        "updated_at": now,
                        "vault_ciphertext": encrypt_vault_text(source_text),
                    },
                },
            )
        ],
        wait=True,
    )
    logger.info("Stored memory %s (%d chars)", doc_id[:8], len(text))
    return doc_id


def upsert_memory(memory_id: str, text: str, *, original_text: str, meta_data: dict | None = None) -> str:
    client, collection, conf = _ensure_collection(feature="Memory migration")
    embedder = _get_embedder(conf)
    now = int(time.time())
    normalized_meta = _normalize_meta_data(meta_data)
    normalized_meta.setdefault("type", "memory")
    normalized_meta.setdefault("created_at", now)
    normalized_meta["updated_at"] = now
    normalized_meta["vault_ciphertext"] = encrypt_vault_text(original_text)
    embedding = embedder.get_embedding(text)
    if embedding is None:
        raise RuntimeError(f"Failed to build embedding for memory {memory_id}")

    client.upsert(
        collection_name=collection,
        points=[
            models.PointStruct(
                id=memory_id,
                vector=embedding,
                payload={
                    "content": text,
                    "meta_data": normalized_meta,
                },
            )
        ],
        wait=True,
    )
    logger.info("Upserted memory %s (%d chars)", memory_id[:8], len(text))
    return memory_id


def _record_to_memory(record, score: float | None = None) -> dict:
    payload = record.payload or {}
    memory = {
        "id": str(record.id),
        "content": payload.get("content", ""),
        "meta_data": _normalize_meta_data(payload.get("meta_data", {})),
    }
    if score is not None:
        memory["score"] = score
    return memory


def _scroll_records(*, with_vectors: bool, limit: int | None = None) -> list:
    client, collection, _ = _ensure_collection(feature="Memory access")
    return _scroll_collection_records(client, collection, with_vectors=with_vectors, limit=limit)


def search(query: str, limit: int = 5, min_score: float = 0.35) -> list[dict]:
    try:
        client, collection, conf = _ensure_collection(feature="Memory search")
        embedder = _get_embedder(conf)
        query_embedding = embedder.get_embedding(query)
        if query_embedding is None:
            logger.warning("Failed to build embedding for query")
            return []

        response = client.query_points(
            collection_name=collection,
            query=query_embedding,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            score_threshold=min_score,
        )
        matches = [_record_to_memory(point, score=float(point.score or 0.0)) for point in response.points]
        if matches:
            logger.info("Qdrant returned %d memory result(s)", len(matches))
            return matches

        rows = [_record_to_memory(record) for record in _scroll_records(with_vectors=False, limit=max(limit * 20, 100))]
        fallback = _select_lexical_matches(rows, query, limit=limit)
        if fallback:
            logger.info("Qdrant lexical fallback recovered %d result(s) for query=%r", len(fallback), query)
        return fallback
    except QdrantConfigurationError as exc:
        logger.warning("Memory search unavailable: %s", exc)
        return []
    except Exception as exc:
        logger.warning("Qdrant lexical fallback failed: %s", exc)
        return []


def get_all(limit: int = 1000) -> list[dict]:
    try:
        return [_record_to_memory(record) for record in _scroll_records(with_vectors=False, limit=limit)]
    except QdrantConfigurationError as exc:
        logger.warning("Memory listing unavailable: %s", exc)
        return []
    except Exception:
        logger.exception("Failed to list all memories")
        return []


def get_all_raw(limit: int = 1000) -> list[dict]:
    return get_all(limit=limit)


def delete_by_id(memory_id: str) -> bool:
    try:
        client, collection, _ = _ensure_collection(feature="Memory deletion")
        client.delete(collection_name=collection, points_selector=[memory_id], wait=True)
        return True
    except Exception as exc:
        logger.warning("Failed to delete memory %s: %s", memory_id, exc)
        return False


def count() -> int:
    try:
        return len(get_all())
    except Exception:
        return 0


def export_collection_snapshot() -> dict:
    client, collection, conf = _ensure_collection(feature="Memory backup export")
    collection_info = client.get_collection(collection)
    vectors = collection_info.config.params.vectors
    vector_size = int(getattr(vectors, "size", 0) or conf.get("embed_dimensions", 1536) or 1536)

    points = []
    for record in _scroll_records(with_vectors=True):
        points.append({
            "id": str(record.id),
            "payload": record.payload or {},
            "vector": record.vector,
        })

    return {
        "collection": collection,
        "vector_size": vector_size,
        "points": points,
    }


def import_collection_snapshot(snapshot: dict) -> None:
    client, _, conf = _get_client(feature="Memory backup import")
    collection = _collection_name(conf)
    vector_size = int(snapshot.get("vector_size") or conf.get("embed_dimensions", 1536) or 1536)

    if client.collection_exists(collection):
        client.delete_collection(collection)

    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )

    raw_points = snapshot.get("points", [])
    if not raw_points:
        return

    batch: list[models.PointStruct] = []
    for item in raw_points:
        batch.append(
            models.PointStruct(
                id=str(item["id"]),
                vector=item.get("vector"),
                payload=item.get("payload", {}),
            )
        )
        if len(batch) >= _SCROLL_BATCH_SIZE:
            client.upsert(collection_name=collection, points=batch, wait=True)
            batch = []

    if batch:
        client.upsert(collection_name=collection, points=batch, wait=True)
