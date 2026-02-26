"""Helpers for pairing code lifecycle and metadata payloads."""

from __future__ import annotations

import time
import uuid
from typing import Optional

from . import config


def pairing_expires_in_s(now: Optional[float] = None) -> Optional[int]:
    """Return remaining pairing lifetime in seconds or `None` for unlimited TTL."""
    exp = getattr(config, "PAIRING_EXPIRES_AT", None)
    if exp is None:
        return None
    try:
        current = float(time.time() if now is None else now)
        return int(max(0.0, float(exp) - current))
    except Exception:
        return None


def pairing_meta(now: Optional[float] = None) -> dict:
    """Build normalized pairing metadata payload."""
    exp = getattr(config, "PAIRING_EXPIRES_AT", None)
    try:
        ttl_s = int(getattr(config, "PAIRING_TTL_S", 0) or 0)
    except Exception:
        ttl_s = 0
    try:
        exp_value = float(exp) if exp is not None else None
    except Exception:
        exp_value = None
    return {
        "pairing_code": str(getattr(config, "PAIRING_CODE", "") or ""),
        "pairing_expires_at": exp_value,
        "pairing_expires_in_s": pairing_expires_in_s(now=now),
        "pairing_ttl_s": int(max(0, ttl_s)),
        "pairing_single_use": bool(getattr(config, "PAIRING_SINGLE_USE", False)),
    }


def rotate_pairing_code(now: Optional[float] = None) -> str:
    """Rotate pairing code and refresh expiration timestamp according to current TTL settings."""
    current = float(time.time() if now is None else now)
    config.PAIRING_CODE = str(uuid.uuid4().int)[:4]
    try:
        ttl_s = int(getattr(config, "PAIRING_TTL_S", 0) or 0)
    except Exception:
        ttl_s = 0
    config.PAIRING_EXPIRES_AT = (current + ttl_s) if ttl_s > 0 else None
    return str(config.PAIRING_CODE)
