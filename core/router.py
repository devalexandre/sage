import logging

from core import config as cfg
from core.license import MemoryLimitExceeded
from core.memory import save_memory
from core.search import search_knowledge

logger = logging.getLogger("sage.router")

_ERROR_MESSAGES = {
    "pt-BR": "Ocorreu um erro ao processar sua solicitacao. Tente novamente mais tarde.",
    "en": "An error occurred while processing your request. Please try again later.",
    "es": "Ocurrio un error al procesar su solicitud. Intente de nuevo mas tarde.",
}


def _error_message() -> str:
    lang = cfg.load().get("language", "pt-BR")
    return _ERROR_MESSAGES.get(lang, _ERROR_MESSAGES["en"])


def _run_with_retry(fn, *args, max_retries: int = 1):
    """Run fn(*args), retry once on failure. Raise on second failure."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn(*args)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning("Attempt %d failed, retrying: %s", attempt + 1, exc)
            else:
                logger.error("All %d attempts failed: %s", max_retries + 1, exc)
    raise last_exc


def route(text: str) -> tuple[str, str]:
    """Route text: question (?) → search, otherwise → store."""
    text = text.strip()
    if text.endswith("?"):
        try:
            answer = _run_with_retry(search_knowledge, text)
        except Exception:
            return "error", _error_message()
        return "answer", answer
    else:
        try:
            response = _run_with_retry(save_memory, text)
        except MemoryLimitExceeded as e:
            return "error", str(e)
        except Exception:
            return "error", _error_message()
        return "memory", response
