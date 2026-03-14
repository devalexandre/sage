"""
RAG module — Qdrant-backed document knowledge for Sage.
PRO feature: upload PDFs, CSVs, Excel files and query them via chat.
"""

import csv
import logging
import shutil
import tempfile
from pathlib import Path

from core import config as cfg
from core.license import require_pro
from core.qdrant_common import QdrantConfigurationError, resolve_qdrant_url

logger = logging.getLogger("sage.rag")

_knowledge = None


def reset_knowledge() -> None:
    """Discard cached knowledge so it is rebuilt with fresh config."""
    global _knowledge
    _knowledge = None


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

    # Default: OpenAI
    from agno.knowledge.embedder.openai import OpenAIEmbedder

    import os
    api_key = conf.get("openai_api_key", "").strip()
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    return OpenAIEmbedder(id=model, dimensions=dims)


def _build_vector_db(conf: dict, embedder):
    from agno.vectordb.qdrant import Qdrant
    from agno.vectordb.search import SearchType
    from agno.knowledge.reranker.sentence_transformer import SentenceTransformerReranker

    return Qdrant(
        collection=conf.get("qdrant_collection", "sage_documents"),
        url=resolve_qdrant_url(conf),
        api_key=conf.get("qdrant_api_key", "") or None,
        embedder=embedder,
        search_type=SearchType.hybrid,
        reranker=SentenceTransformerReranker(model="BAAI/bge-reranker-v2-m3"),
    )


def get_knowledge(conf: dict | None = None):
    """Return a Knowledge instance or None if Qdrant is not configured."""
    global _knowledge
    if _knowledge is not None:
        return _knowledge

    if conf is None:
        conf = cfg.load()

    qdrant_url = resolve_qdrant_url(conf)
    if not qdrant_url:
        return None  # user hasn't configured Qdrant yet

    try:
        from agno.knowledge import Knowledge

        embedder = _build_embedder(conf)
        vector_db = _build_vector_db(conf, embedder)
        _knowledge = Knowledge(
            name="sage_documents",
            vector_db=vector_db,
            max_results=10,
        )
        logger.info("Knowledge initialised (Qdrant at %s)", qdrant_url)
        return _knowledge
    except Exception as e:
        logger.error("Failed to initialise Knowledge: %s", e)
        return None


def _convert_excel_to_csv(src: Path) -> Path:
    """Convert an .xls/.xlsx file to a temporary CSV and return its path."""
    import openpyxl

    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb.active
    tmp = Path(tempfile.mktemp(suffix=".csv"))
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            writer.writerow(row)
    wb.close()
    return tmp


_ALLOWED_EXTENSIONS = {".pdf", ".csv", ".xls", ".xlsx"}


def ingest_file(file_path: str) -> str:
    """
    Ingest a document into the Qdrant knowledge base.
    Raises ProFeatureRequired for free users.
    Returns a status message.
    """
    require_pro("Document upload")

    src = Path(file_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = src.suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
        )

    conf = cfg.load()
    qdrant_url = resolve_qdrant_url(conf)
    if not qdrant_url:
        raise QdrantConfigurationError(
            "Document upload requires Qdrant. Configure a Qdrant URL in Settings > Documents "
            "or enable 'Run Qdrant with Docker'."
        )
    knowledge = get_knowledge(conf)
    if knowledge is None:
        raise RuntimeError(
            "Qdrant is not configured. "
            "Go to Settings > Documents to set your Qdrant URL and API key."
        )

    tmp_csv: Path | None = None
    ingest_path = src

    try:
        # Excel → convert to CSV first
        if ext in (".xls", ".xlsx"):
            tmp_csv = _convert_excel_to_csv(src)
            ingest_path = tmp_csv

        # Ingest via agno Knowledge (auto-selects reader by extension)
        # Retry once on transient Qdrant errors (e.g. missing index)
        try:
            knowledge.insert(path=str(ingest_path), upsert=True)
        except Exception as first_err:
            logger.warning("First insert attempt failed, retrying: %s", first_err)
            knowledge.insert(path=str(ingest_path), upsert=True)

        # Copy original to documents folder
        docs_dir = cfg.get_documents_path(conf)
        dest = docs_dir / src.name
        if dest != src:
            shutil.copy2(str(src), str(dest))

        logger.info("Indexed: %s", src.name)
        return f"Indexed: {src.name}"
    finally:
        if tmp_csv and tmp_csv.exists():
            tmp_csv.unlink(missing_ok=True)
