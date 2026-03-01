from core.agent import store_fact
from core.license import MemoryLimitExceeded, enforce_limit
from db.sqlite import insert_entry


def save_memory(text: str) -> str:
    """Persist a note to SQLite log and index it in the agent's memory."""
    enforce_limit()
    insert_entry(text, kind="memory")
    return store_fact(text)
