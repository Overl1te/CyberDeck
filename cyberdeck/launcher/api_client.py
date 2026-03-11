"""Small HTTP client used by launcher UI to talk to local API."""

from typing import Any, Optional

import requests


class LauncherApiClient:
    """Thin wrapper around `requests` with stable local API endpoints."""

    def __init__(self, base_url: str, verify: bool | str = True) -> None:
        """Initialize LauncherApiClient state and collaborator references."""
        self.base_url = str(base_url or "").rstrip("/")
        self.verify = verify

    def configure(self, base_url: str, verify: bool | str = True) -> None:
        """Update target API base URL and TLS verification mode."""
        self.base_url = str(base_url or "").rstrip("/")
        self.verify = verify

    def _get(self, path: str, timeout: float):
        """Execute GET request to a relative API path."""
        return requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            timeout=timeout,
            verify=self.verify,
        )

    def _post(self, path: str, payload: Optional[dict[str, Any]] = None, timeout: float = 2.0):
        """Execute POST request with JSON payload to a relative API path."""
        return requests.post(
            f"{self.base_url}/{path.lstrip('/')}",
            json=payload,
            timeout=timeout,
            verify=self.verify,
        )

    @staticmethod
    def describe_exception(exc: BaseException) -> str:
        """Return concise user-facing explanation for transport/runtime exceptions."""
        if isinstance(exc, requests.exceptions.SSLError):
            return "TLS verification failed"
        if isinstance(exc, requests.exceptions.Timeout):
            return "request timeout"
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "connection failed"
        text = str(exc or "").strip()
        return text or exc.__class__.__name__

    @staticmethod
    def json_dict(response: Any, *, default: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Decode response JSON as dict with predictable fallback."""
        fallback = {} if default is None else dict(default)
        try:
            payload = response.json()
        except Exception:
            return fallback
        if isinstance(payload, dict):
            return payload
        return fallback

    @classmethod
    def describe_api_error(cls, response: Any, *, default: str = "API error") -> str:
        """Extract readable API error text from structured response payload."""
        status_code = int(getattr(response, "status_code", 0) or 0)
        payload = cls.json_dict(response)
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}

        code = str(error.get("code") or "").strip()
        title = str(error.get("title") or "").strip()
        hint = str(error.get("hint") or "").strip()
        detail = str(payload.get("detail") or "").strip()

        pieces: list[str] = []
        if code:
            pieces.append(code)
        if title:
            pieces.append(title)
        if hint:
            pieces.append(hint)
        if pieces:
            return " | ".join(pieces)
        if detail:
            return detail
        if status_code > 0:
            return f"HTTP {status_code}"
        return str(default or "API error")

    def get_info(self, timeout: float = 1.0):
        """Retrieve data required to get info."""
        # Read-path helpers should avoid mutating shared state where possible.
        return self._get("info", timeout=timeout)

    def get_updates(self, timeout: float = 2.5, force_refresh: bool = False):
        """Retrieve release update status from local API."""
        path = "updates?force_refresh=1" if force_refresh else "updates"
        return self._get(path, timeout=timeout)

    def get_qr_payload(self, timeout: float = 1.0):
        """Retrieve data required to get qr payload."""
        # Read-path helpers should avoid mutating shared state where possible.
        return self._get("qr_payload", timeout=timeout)

    def get_events(self, since_id: int = 0, limit: int = 100, timeout: float = 1.5):
        """Retrieve local server events for launcher notifications."""
        return self._get(f"events?since_id={int(since_id)}&limit={int(limit)}", timeout=timeout)

    def get_pending_devices(self, timeout: float = 1.5):
        """Retrieve pending device approval queue."""
        return self._get("pending_devices", timeout=timeout)

    def get_trusted_devices(self, timeout: float = 1.5):
        """Retrieve approved devices list with activity metadata."""
        return self._get("trusted_devices", timeout=timeout)

    def get_security_state(self, timeout: float = 1.5):
        """Retrieve current remote-input lock state."""
        return self._get("security_state", timeout=timeout)

    def device_approve(self, token: str, allow: bool, timeout: float = 2.0):
        """Approve or deny a pending device session."""
        return self._post("device_approve", {"token": token, "allow": bool(allow)}, timeout=timeout)

    def device_rename(self, token: str, alias: str = "", note: str = "", timeout: float = 2.0):
        """Update alias/note for a trusted device."""
        payload = {"token": str(token or ""), "alias": str(alias or ""), "note": str(note or "")}
        return self._post("device_rename", payload, timeout=timeout)

    def device_disconnect(self, token: str, timeout: float = 2.0):
        """Call local API endpoint to disconnect a device session."""
        return self._post("device_disconnect", {"token": token}, timeout=timeout)

    def device_delete(self, token: str, timeout: float = 3.0):
        """Call local API endpoint to delete a device session."""
        return self._post("device_delete", {"token": token}, timeout=timeout)

    def device_settings(self, payload: dict[str, Any], timeout: float = 2.0):
        """Call local API endpoint to update per-device settings."""
        return self._post("device_settings", payload, timeout=timeout)

    def trigger_file(self, payload: dict[str, Any], timeout: float = 4.0):
        """Trigger file."""
        return self._post("trigger_file", payload, timeout=timeout)

    def regenerate_code(self, timeout: float = 2.0):
        """Regenerate code."""
        return self._post("regenerate_code", payload=None, timeout=timeout)

    def set_input_lock(self, locked: bool, reason: str = "", actor: str = "launcher", timeout: float = 2.0):
        """Enable or disable remote-input lock."""
        payload = {"locked": bool(locked), "reason": str(reason or ""), "actor": str(actor or "launcher")}
        return self._post("input_lock", payload=payload, timeout=timeout)

    def panic_mode(self, keep_token: str = "", lock_input: bool = True, reason: str = "", timeout: float = 3.0):
        """Disconnect/revoke sessions and optionally lock remote input."""
        payload = {"keep_token": str(keep_token or ""), "lock_input": bool(lock_input), "reason": str(reason or "")}
        return self._post("panic_mode", payload=payload, timeout=timeout)
