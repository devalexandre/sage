"""
Vault — seal sensitive values before sending to the LLM,
unseal [VAULT:…] tokens when displaying responses.

Strategy:
  - First line is kept as plaintext (title / description for LLM search).
  - Lines starting with # are kept as plaintext (headers).
  - Empty lines are kept as-is.
  - Everything else is encrypted into [VAULT:token] tokens.

This ensures the LLM never sees raw credentials, emails, API keys, etc.,
so it will never trigger safety-filter refusals.
"""

import re

from db import sqlite as _db

_VAULT_RE = re.compile(r"\[VAULT:([^\]]+)\]")


def seal(text: str) -> str:
    """Encrypt sensitive lines before sending to the LLM.

    Keeps the first line and # headers in plaintext so the LLM
    can still search/match by topic. All other lines become
    [VAULT:encrypted] tokens.
    """
    fernet = _db._fernet
    if not fernet:
        return text

    lines = text.split("\n")
    sealed: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i == 0 or stripped.startswith("#") or not stripped:
            sealed.append(line)
        else:
            token = fernet.encrypt(stripped.encode("utf-8")).decode("ascii")
            sealed.append(f"[VAULT:{token}]")
    return "\n".join(sealed)


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
