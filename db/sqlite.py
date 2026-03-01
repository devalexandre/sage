import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DB_PATH = Path.home() / ".sage" / "history.db"

# Set once at startup via set_fernet(); None = no encryption (legacy / dev mode)
_fernet: Fernet | None = None


def set_fernet(fernet: Fernet) -> None:
    """Call once after loading the encryption key. All subsequent reads/writes are encrypted."""
    global _fernet
    _fernet = fernet


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            text       TEXT    NOT NULL,
            kind       TEXT    NOT NULL DEFAULT 'memory',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def insert_entry(text: str, kind: str = "memory") -> int:
    stored = _fernet.encrypt(text.encode()).decode() if _fernet else text
    conn = _connect()
    cursor = conn.execute(
        "INSERT INTO entries (text, kind) VALUES (?, ?)", (stored, kind)
    )
    conn.commit()
    entry_id = cursor.lastrowid
    conn.close()
    return entry_id


def recent_entries(limit: int = 20) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, text, kind, created_at FROM entries ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        text = r[1]
        if _fernet:
            try:
                text = _fernet.decrypt(text.encode()).decode()
            except (InvalidToken, Exception):
                pass  # legacy plaintext row — return as-is
        result.append({"id": r[0], "text": text, "kind": r[2], "created_at": r[3]})
    return result


def count_entries(kind: str = "memory") -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE kind = ?", (kind,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0
