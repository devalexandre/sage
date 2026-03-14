import shutil

from qdrant_client import QdrantClient


class QdrantConfigurationError(RuntimeError):
    pass


def docker_installed() -> bool:
    return shutil.which("docker") is not None


def resolve_qdrant_url(conf: dict) -> str:
    url = conf.get("qdrant_url", "").strip()
    if url:
        return url
    if conf.get("qdrant_docker", False):
        return "http://localhost:6333"
    return ""


def ensure_qdrant_configured(conf: dict, *, feature: str) -> str:
    if conf.get("qdrant_docker", False) and not docker_installed():
        raise QdrantConfigurationError(
            f"{feature} requires Qdrant via Docker, but Docker was not found. "
            "Install Docker Desktop or configure a Qdrant URL in Settings > Documents."
        )

    url = resolve_qdrant_url(conf)
    if not url:
        raise QdrantConfigurationError(
            f"{feature} requires Qdrant. Configure a Qdrant URL in Settings > Documents "
            "or enable 'Run Qdrant with Docker'."
        )
    return url


def build_qdrant_client(conf: dict, *, feature: str) -> QdrantClient:
    url = ensure_qdrant_configured(conf, feature=feature)
    return QdrantClient(
        url=url,
        api_key=conf.get("qdrant_api_key", "").strip() or None,
    )

