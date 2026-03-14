"""
Local encryption for ~/.sage/history.db using Fernet (AES-128-CBC + HMAC-SHA256).

Key lifecycle:
  - First run: generate 32 random bytes → write to ~/.sage/enc.key (chmod 600)
               format as 8-group hex recovery phrase
  - Normal run: read 32 bytes → derive Fernet key
  - Recovery:   user pastes recovery phrase → reconstruct enc.key
"""

import base64
import os
import stat

from cryptography.fernet import Fernet, InvalidToken

from core.paths import DATA_DIR, ensure_data_dir

KEY_PATH = DATA_DIR / "enc.key"


class EncryptionKeyMissing(Exception):
    pass


class EncryptionKeyCorrupted(Exception):
    pass


# ── key lifecycle ──────────────────────────────────────────────────────────────

def key_exists() -> bool:
    return KEY_PATH.exists()


def first_run_init() -> str:
    """Generate key on first run. Returns the recovery phrase to show the user."""
    raw = os.urandom(32)
    _write_key(raw)
    return _format_phrase(raw)


def load_key() -> Fernet:
    """Load the Fernet instance from disk. Raises EncryptionKeyMissing / Corrupted."""
    if not KEY_PATH.exists():
        raise EncryptionKeyMissing("Encryption key not found. Recovery required.")
    raw = KEY_PATH.read_bytes()
    if len(raw) != 32:
        raise EncryptionKeyCorrupted(
            f"Encryption key has wrong length ({len(raw)} bytes, expected 32)."
        )
    b64_key = base64.urlsafe_b64encode(raw)
    return Fernet(b64_key)


def reconstruct_from_phrase(phrase: str) -> bool:
    """
    Parse a recovery phrase and recreate enc.key.
    Returns True on success, False if phrase is invalid.
    """
    try:
        raw = _parse_phrase(phrase)
    except Exception:
        return False
    if len(raw) != 32:
        return False
    _write_key(raw)
    return True


# ── encrypt / decrypt text ────────────────────────────────────────────────────

def encrypt_text(plaintext: str, fernet: Fernet) -> str:
    """Return URL-safe base64 ciphertext string."""
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(ciphertext: str, fernet: Fernet) -> str:
    """Decrypt ciphertext. Raises InvalidToken if wrong key or corrupted."""
    return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")


# ── internal helpers ──────────────────────────────────────────────────────────

def _write_key(raw: bytes) -> None:
    ensure_data_dir()
    KEY_PATH.write_bytes(raw)
    try:
        KEY_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception:
        pass


def _format_phrase(raw: bytes) -> str:
    """64 hex chars → 8 groups of 8 separated by '-'."""
    hex_str = raw.hex().upper()
    return "-".join(hex_str[i:i+8] for i in range(0, 64, 8))


def _parse_phrase(phrase: str) -> bytes:
    """Remove dashes/spaces, decode hex → 32 bytes."""
    clean = phrase.replace("-", "").replace(" ", "").strip().upper()
    return bytes.fromhex(clean)
