"""
HTTP client for the Sage Go API.
Uses only stdlib (urllib) — no extra dependencies.
"""

import json
import platform
import urllib.error
import urllib.request
from typing import Any

from core import config as cfg


class AuthError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class NetworkError(Exception):
    pass


class AuthClient:
    def __init__(self, api_url: str | None = None) -> None:
        self._base = (api_url or cfg.load().get("api_url", "http://localhost:8080")).rstrip("/")

    # ── auth ──────────────────────────────────────────────────────────────────

    def register(self, email: str, password: str) -> dict:
        return self._post("/auth/register", {"email": email, "password": password})

    def login(self, email: str, password: str) -> dict:
        return self._post("/auth/login", {"email": email, "password": password})

    def refresh(self, refresh_token: str) -> dict:
        return self._post("/auth/refresh", {"refresh_token": refresh_token})

    def me(self, access_token: str) -> dict:
        return self._get("/auth/me", token=access_token)

    # ── license ───────────────────────────────────────────────────────────────

    def check_subscriber(self, access_token: str,
                         device_id: str, device_name: str = "",
                         order_id: str = "") -> dict:
        """Verify subscription via Gumroad and sync plan in DB."""
        payload: dict = {
            "device_id":   device_id,
            "device_name": device_name or platform.node(),
            "platform":    platform.system().lower(),
        }
        if order_id:
            payload["order_id"] = order_id
        return self._post("/license/check", payload, token=access_token)

    def license_status(self, access_token: str, device_id: str) -> dict:
        return self._get(f"/license/status?device_id={device_id}", token=access_token)

    def deactivate_device(self, access_token: str, device_id: str) -> None:
        self._delete("/license/device", {"device_id": device_id}, token=access_token)

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _post(self, path: str, body: dict, token: str | None = None) -> dict:
        return self._request("POST", path, body=body, token=token)

    def _get(self, path: str, token: str | None = None) -> dict:
        return self._request("GET", path, token=token)

    def _delete(self, path: str, body: dict | None = None, token: str | None = None) -> dict:
        return self._request("DELETE", path, body=body, token=token)

    def _request(self, method: str, path: str,
                 body: dict | None = None, token: str | None = None) -> dict:
        url = self._base + path
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                payload: Any = json.loads(e.read())
                msg = payload.get("error", str(e))
            except Exception:
                msg = str(e)
            raise AuthError(e.code, msg)
        except OSError as e:
            raise NetworkError(f"Cannot reach Sage API at {self._base}: {e}") from e
