import json
from pathlib import Path

VERSION = "0.1.0"

CONFIG_PATH = Path.home() / ".sage" / "config.json"

_DEFAULTS: dict = {
    # Auth
    "auth_token":    "",
    "refresh_token": "",
    "user_id":       "",
    "user_email":    "",
    "user_plan":     "free",
    "data_migration_version": 0,
    "license_key":   "",
    "device_id":     "",
    "api_url":       "https://sage-api-efi8.onrender.com",
    # Model provider
    "provider": "openai",
    # OpenAI
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    # Ollama
    "ollama_host": "http://localhost:11434",
    "ollama_model": "",
    # LM Studio
    "lmstudio_base_url": "http://127.0.0.1:1234/v1",
    "lmstudio_model": "",
    # vLLM
    "vllm_base_url": "http://localhost:8000/v1",
    "vllm_model": "",
    "vllm_api_key": "",
    # Hotkey
    "hotkey": "F10",
    # Language
    "language": "pt-BR",
    # Milvus (memory vector store)
    "milvus_uri": "~/.sage/milvus.db",
    "milvus_token": "",
    "milvus_collection": "sage_memories",
    # RAG / Documents
    "qdrant_url": "",
    "qdrant_api_key": "",
    "qdrant_collection": "sage_documents",
    "embed_provider": "openai",
    "embed_model": "text-embedding-3-small",
    "embed_dimensions": 1536,
    "documents_path": "",
    # Forget (memory retention)
    "forget_retention_days": 30,
}


def get_documents_path(conf: dict | None = None) -> Path:
    """Return the resolved documents folder, creating it if needed."""
    if conf is None:
        conf = load()
    custom = conf.get("documents_path", "").strip()
    p = Path(custom) if custom else Path.home() / "Documents" / "Sage"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
