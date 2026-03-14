"""
Local license helpers and stable device identity.
"""

import hashlib
import platform
import uuid

from core.paths import DATA_DIR, ensure_data_dir

_DEVICE_ID_PATH = DATA_DIR / "device_id"


# ── device identity ───────────────────────────────────────────────────────────

def get_device_id() -> str:
    """Return a stable per-device hex fingerprint (cached in ~/.sage/device_id)."""
    if _DEVICE_ID_PATH.exists():
        return _DEVICE_ID_PATH.read_text().strip()
    raw = f"{platform.node()}-{uuid.getnode()}-{platform.machine()}"
    device_id = hashlib.sha256(raw.encode()).hexdigest()
    ensure_data_dir()
    _DEVICE_ID_PATH.write_text(device_id)
    return device_id


# ── memory count & limit ──────────────────────────────────────────────────────

FREE_MEMORY_LIMIT = 500


class MemoryLimitExceeded(Exception):
    pass


class ProFeatureRequired(Exception):
    pass


def require_pro(feature: str = "This feature") -> None:
    """Raise ProFeatureRequired if the current plan is not pro."""
    from core import config as cfg
    conf = cfg.load()
    if conf.get("user_plan", "free") != "pro":
        raise ProFeatureRequired(f"{feature} requires Sage Pro.")


def count_memories() -> int:
    from core.sqlite_memory import count
    return count()


def enforce_limit() -> None:
    """Raise MemoryLimitExceeded if the free plan memory limit is reached."""
    from core import config as cfg
    conf = cfg.load()
    plan = conf.get("user_plan", "free")
    if plan == "pro":
        return  # unlimited
    current = count_memories()
    if current >= FREE_MEMORY_LIMIT:
        raise MemoryLimitExceeded(
            f"Memory limit reached ({current}/{FREE_MEMORY_LIMIT}). "
            "Subscribe to Sage Pro for unlimited memories."
        )


# ── token refresh helper ──────────────────────────────────────────────────────

def check_and_refresh_token(client, conf: dict) -> dict:
    """
    If the access token appears expired, attempt a silent refresh.
    Updates and saves conf on success; raises on failure.
    client: AuthClient instance
    """
    import base64, json as _json, time as _time
    token = conf.get("auth_token", "")
    if not token:
        raise ValueError("No auth token")

    # Decode JWT payload (no signature check — just inspect exp claim)
    try:
        parts = token.split(".")
        payload_b64 = parts[1] + "=="  # pad
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp", 0)
        if exp > _time.time() + 30:
            return conf  # still valid
    except Exception:
        pass  # Can't decode — attempt refresh anyway

    # Token expired or unreadable — try refresh
    new_tokens = client.refresh(conf.get("refresh_token", ""))
    conf["auth_token"]    = new_tokens["access_token"]
    conf["refresh_token"] = new_tokens["refresh_token"]

    from core import config as cfg
    cfg.save(conf)
    return conf
