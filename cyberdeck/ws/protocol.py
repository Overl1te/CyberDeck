"""Helpers for the WebSocket control protocol."""

from typing import Any, Mapping

from ..protocol import protocol_payload


_TEXT_EVENT_TYPES = {"text", "type_text", "input_text", "insert_text", "keyboard_text"}
_TEXT_FIELDS = ("text", "value", "message", "payload", "data")


def is_text_event_type(msg_type: str) -> bool:
    """Return True when incoming message type should be interpreted as text input."""
    return str(msg_type or "").strip().lower() in _TEXT_EVENT_TYPES


def extract_text_payload(data: Mapping[str, Any] | Any) -> str:
    """Extract the first supported plain-text field from a WS payload."""
    if not isinstance(data, Mapping):
        return ""
    for field in _TEXT_FIELDS:
        if field not in data:
            continue
        val = data.get(field)
        if val is None:
            continue
        if isinstance(val, (dict, list, tuple, set)):
            continue
        text = str(val)
        if text:
            return text
    return ""


def build_server_hello(msg_type: str, hb_interval_s: int, hb_timeout_s: int) -> dict:
    """Build normalized server hello payload used by the WS handshake."""
    return {
        "type": str(msg_type or "hello"),
        **protocol_payload(),
        "heartbeat_interval_ms": int(hb_interval_s * 1000),
        "heartbeat_timeout_ms": int(hb_timeout_s * 1000),
    }

