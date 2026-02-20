"""Server protocol metadata shared across HTTP and WebSocket endpoints."""

import time
from typing import Any, Dict

from . import config


def protocol_features() -> Dict[str, Any]:
    """Return stable feature flags supported by the current server build."""
    return {
        "stream_offer_v2": True,
        "stream_backend_select": True,
        "stream_diag": True,
        "ws_cursor": True,
        "ws_heartbeat": True,
        "file_transfer_resume": True,
        "file_transfer_checksum": True,
    }


def protocol_payload() -> Dict[str, Any]:
    """Build protocol metadata payload with runtime config and current server time."""
    return {
        "protocol_version": int(getattr(config, "PROTOCOL_VERSION", 2)),
        "min_supported_protocol_version": int(getattr(config, "MIN_SUPPORTED_PROTOCOL_VERSION", 1)),
        "server_version": str(config.VERSION),
        "server_time_ms": int(time.time() * 1000),
        "features": protocol_features(),
    }


