"""
Vault helpers for local encryption and retrieval-safe redaction.

- Full note text stays encrypted locally.
- Retrieval text is redacted so embeddings and LLM prompts keep context
  without exposing raw secrets to remote providers.
- Legacy [VAULT:...] tokens are still supported for older memories.
"""

import re
from typing import Any

from db import sqlite as _db

_VAULT_RE = re.compile(r"\[VAULT:([^\]]+)\]")

_KEY_VALUE_RE = re.compile(r"^(\s*[^:\n]{1,80}:\s*)(.+?)\s*$")
_SENSITIVE_LABEL_RE = re.compile(
    r"(senha|password|passwd|pwd|token|secret|api[_ -]?key|access[_ -]?key|"
    r"client[_ -]?secret|private[_ -]?key|bearer|cnpj|cpf|email|e-mail|telefone|phone)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ_RE = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}(?!\d)")
_LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_\-]{20,}\b")

_MASKS = {
    "senha": "[PASSWORD]",
    "password": "[PASSWORD]",
    "passwd": "[PASSWORD]",
    "pwd": "[PASSWORD]",
    "token": "[TOKEN]",
    "secret": "[SECRET]",
    "api_key": "[API_KEY]",
    "access_key": "[ACCESS_KEY]",
    "client_secret": "[CLIENT_SECRET]",
    "private_key": "[PRIVATE_KEY]",
    "bearer": "[TOKEN]",
    "cnpj": "[CNPJ]",
    "cpf": "[CPF]",
    "email": "[EMAIL]",
    "phone": "[PHONE]",
}


def encrypt_text(text: str) -> str:
    """Encrypt full text for local-only storage."""
    fernet = _db._fernet
    if not fernet:
        return text
    return fernet.encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_text(text: str) -> str:
    """Decrypt local ciphertext, falling back to plaintext when needed."""
    fernet = _db._fernet
    if not fernet:
        return text
    try:
        return fernet.decrypt(text.encode("ascii")).decode("utf-8")
    except Exception:
        return text


def _mask_for_label(label: str) -> str:
    lowered = label.lower().replace("-", "_").replace(" ", "_")
    for key, mask in _MASKS.items():
        if key in lowered:
            return mask
    return "[SECRET]"


def _redact_inline_values(text: str) -> str:
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _CPF_RE.sub("[CPF]", text)
    text = _CNPJ_RE.sub("[CNPJ]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    return _LONG_SECRET_RE.sub("[SECRET]", text)


def sanitize_for_retrieval(text: str) -> str:
    """Redact sensitive values while preserving searchable context."""
    lines: list[str] = []
    for line in text.splitlines():
        match = _KEY_VALUE_RE.match(line)
        if match and _SENSITIVE_LABEL_RE.search(match.group(1)):
            lines.append(f"{match.group(1)}{_mask_for_label(match.group(1))}")
            continue
        lines.append(_redact_inline_values(line))
    return "\n".join(lines)


def extract_full_text(memory: dict[str, Any]) -> str:
    """Return full local note text for a retrieved memory."""
    meta = memory.get("meta_data", {}) or {}
    if isinstance(meta, str):
        meta = {}

    ciphertext = meta.get("vault_ciphertext", "")
    if ciphertext:
        return decrypt_text(ciphertext)
    return unseal(memory.get("content", ""))


def retrieval_text(memory: dict[str, Any]) -> str:
    """Return retrieval-safe text for prompts and embedding fallback."""
    full_text = extract_full_text(memory)
    return sanitize_for_retrieval(full_text)


def seal(text: str) -> str:
    """Backward-compatible alias retained for older code paths."""
    return sanitize_for_retrieval(text)


def unseal(text: str) -> str:
    """Decrypt all [VAULT:…] tokens found in a string."""
    fernet = _db._fernet
    if not fernet:
        return text

    def _decrypt(match: re.Match) -> str:
        try:
            return fernet.decrypt(match.group(1).encode("ascii")).decode("utf-8")
        except Exception:
            return match.group(0)  # return token as-is if decryption fails

    return _VAULT_RE.sub(_decrypt, text)
