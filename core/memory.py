from core.agent import store_fact
from core.license import MemoryLimitExceeded, enforce_limit
from db.sqlite import insert_entry


def save_memory(text: str) -> str:
    """Persist a note to the local history log and SQLite memory store."""
    enforce_limit()
    result = store_fact(text)
    insert_entry(text, kind="memory")
    return result
