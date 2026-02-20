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
