from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from .sessions import DeviceManager


device_manager = DeviceManager()
device_manager.load_sessions()

running_loop: Optional[asyncio.AbstractEventLoop] = None


class LocalEventStore:
    """Thread-safe in-memory local event stream for launcher notifications."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[dict] = []
        self._next_id = 1
        self._max_events = 512

    def emit(self, event_type: str, *, title: str = "", message: str = "", payload: Optional[dict] = None) -> int:
        """Append a local event and return assigned event id."""
        evt = {
            "id": 0,
            "ts": int(time.time()),
            "type": str(event_type or "").strip() or "event",
            "title": str(title or "").strip(),
            "message": str(message or "").strip(),
            "payload": dict(payload or {}),
        }
        with self._lock:
            evt["id"] = int(self._next_id)
            self._next_id += 1
            self._events.append(evt)
            if len(self._events) > self._max_events:
                cut = len(self._events) - self._max_events
                if cut > 0:
                    self._events = self._events[cut:]
            return int(evt["id"])

    def list_after(self, last_id: int, *, limit: int = 100) -> dict:
        """Return events with id greater than `last_id`."""
        try:
            cursor = int(last_id or 0)
        except Exception:
            cursor = 0
        take = max(1, min(500, int(limit or 100)))
        with self._lock:
            rows = [dict(x) for x in self._events if int(x.get("id") or 0) > cursor]
            rows = rows[:take]
            latest = int(self._events[-1]["id"]) if self._events else cursor
        return {"events": rows, "latest_id": latest}


local_events = LocalEventStore()


class InputGuardState:
    """Thread-safe remote-input lock state used by websocket handlers and local API."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._locked = False
        self._reason = ""
        self._actor = "system"
        self._updated_ts = float(time.time())

    def set_locked(self, locked: bool, *, reason: str = "", actor: str = "system") -> dict:
        """Set lock state and return a normalized snapshot payload."""
        with self._lock:
            self._locked = bool(locked)
            self._reason = str(reason or "").strip()
            self._actor = str(actor or "system").strip() or "system"
            self._updated_ts = float(time.time())
            return self.snapshot()

    def is_locked(self) -> bool:
        """Return current remote-input lock flag."""
        with self._lock:
            return bool(self._locked)

    def snapshot(self) -> dict:
        """Return the current remote-input lock snapshot."""
        with self._lock:
            return {
                "locked": bool(self._locked),
                "reason": str(self._reason),
                "actor": str(self._actor),
                "updated_ts": float(self._updated_ts),
            }


input_guard = InputGuardState()
