from core.license import MemoryLimitExceeded
from core.memory import save_memory
from core.search import search_knowledge


def route(text: str) -> tuple[str, str]:
    """Route text: question (?) → search, otherwise → store."""
    text = text.strip()
    if text.endswith("?"):
        answer = search_knowledge(text)
        return "answer", answer
    else:
        try:
            response = save_memory(text)
        except MemoryLimitExceeded as e:
            return "error", str(e)
        return "memory", response
