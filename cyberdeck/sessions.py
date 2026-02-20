import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

try:
    from fastapi import WebSocket
except Exception:  # pragma: no cover - fallback for minimal test environments
    class WebSocket:  # type: ignore[override]
        pass

from . import config
from .logging_config import log


@dataclass
class DeviceSession:
    device_id: str
    device_name: str
    ip: str
    token: str = field(default_factory=lambda: str(uuid.uuid4()))
    websocket: Optional[WebSocket] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    created_ts: float = field(default_factory=lambda: time.time())
    last_seen_ts: float = field(default_factory=lambda: time.time())
    last_ws_seen_ts: float = field(default_factory=lambda: 0.0)


class DeviceManager:
    def __init__(self) -> None:
        """Initialize DeviceManager state and collaborator references."""
        self.sessions: Dict[str, DeviceSession] = {}
        self._lock = threading.RLock()

    def _touch(self, s: DeviceSession) -> None:
        """Refresh activity timestamp for the tracked session."""
        try:
            s.last_seen_ts = time.time()
        except Exception:
            pass

    def _is_expired(self, s: DeviceSession, now: Optional[float] = None) -> bool:
        """Return whether expired."""
        now = float(time.time() if now is None else now)
        try:
            ttl = int(config.SESSION_TTL_S or 0)
            if ttl > 0 and (now - float(s.created_ts)) > ttl:
                return True
        except Exception:
            pass
        try:
            idle = int(config.SESSION_IDLE_TTL_S or 0)
            if idle > 0 and (now - float(s.last_seen_ts)) > idle:
                return True
        except Exception:
            pass
        return False

    def _prune_expired_locked(self) -> bool:
        """Remove expired sessions while holding manager lock."""
        now = time.time()
        expired = [t for t, s in list(self.sessions.items()) if self._is_expired(s, now=now)]
        if not expired:
            return False
        for t in expired:
            try:
                self.sessions.pop(t, None)
            except Exception:
                pass
        return True

    def _enforce_max_sessions_locked(self) -> bool:
        """Trim sessions to the configured maximum while locked."""
        try:
            max_s = int(config.MAX_SESSIONS or 0)
        except Exception:
            max_s = 0
        if max_s <= 0:
            return False
        if len(self.sessions) <= max_s:
            return False

        items = list(self.sessions.items())
        items.sort(key=lambda kv: float(getattr(kv[1], "last_seen_ts", 0.0) or 0.0))
        to_evict = max(0, len(items) - max_s)
        if to_evict <= 0:
            return False
        for token, _s in items[:to_evict]:
            try:
                self.sessions.pop(token, None)
            except Exception:
                pass
        return True

    def _save_sessions_locked(self) -> None:
        """Save sessions locked."""
        data = {
            t: {
                "device_id": s.device_id,
                "device_name": s.device_name,
                "ip": s.ip,
                "settings": s.settings,
                "created_ts": float(getattr(s, "created_ts", 0.0) or 0.0),
                "last_seen_ts": float(getattr(s, "last_seen_ts", 0.0) or 0.0),
                "last_ws_seen_ts": float(getattr(s, "last_ws_seen_ts", 0.0) or 0.0),
            }
            for t, s in self.sessions.items()
        }
        tmp_path = config.SESSION_FILE + f".tmp-{uuid.uuid4().hex[:8]}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, config.SESSION_FILE)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    @staticmethod
    def _looks_like_test_session(s: DeviceSession) -> bool:
        """Detect synthetic sessions created by tests or local tooling."""
        try:
            ip = str(getattr(s, "ip", "") or "").strip().lower()
            did = str(getattr(s, "device_id", "") or "").strip().lower()
            name = str(getattr(s, "device_name", "") or "").strip()
        except Exception:
            return False

        if ip == "testclient":
            return True
        if did.startswith("test-") or did.startswith("qr-test-"):
            return True
        if did in {"upload-tests", "api-behavior-1"}:
            return True
        if name in {"CI Device", "QR Device", "Upload Tests", "API Behavior"}:
            return True
        return False

    def authorize(self, device_id: str, name: str, ip: str) -> str:
        """Authorize the target operation."""
        with self._lock:
            self._prune_expired_locked()
            for t, s in self.sessions.items():
                if s.device_id == device_id:
                    s.ip = ip
                    s.device_name = name
                    self._touch(s)
                    self._save_sessions_locked()
                    return t

            self._enforce_max_sessions_locked()
            s = DeviceSession(device_id=device_id, device_name=name, ip=ip)
            self.sessions[s.token] = s
            self._save_sessions_locked()
            return s.token

    def save_sessions(self) -> None:
        """Save sessions."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        try:
            with self._lock:
                self._save_sessions_locked()
        except Exception:
            log.exception("Failed to save sessions")

    def load_sessions(self) -> None:
        """Retrieve data required to load sessions."""
        # Read-path helpers should avoid mutating shared state where possible.
        try:
            loaded: Dict[str, DeviceSession] = {}
            if os.path.exists(config.SESSION_FILE):
                with open(config.SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for t, i in (data or {}).items():
                        loaded[t] = DeviceSession(
                            device_id=i.get("device_id"),
                            device_name=i.get("device_name"),
                            ip=i.get("ip"),
                            token=t,
                            settings=i.get("settings") or {},
                            created_ts=float(i.get("created_ts") or time.time()),
                            last_seen_ts=float(i.get("last_seen_ts") or time.time()),
                            last_ws_seen_ts=float(i.get("last_ws_seen_ts") or i.get("last_seen_ts") or 0.0),
                        )
            with self._lock:
                self.sessions = loaded
                dirty = False
                test_tokens = [t for t, s in list(self.sessions.items()) if self._looks_like_test_session(s)]
                if test_tokens:
                    for t in test_tokens:
                        try:
                            self.sessions.pop(t, None)
                        except Exception:
                            pass
                    dirty = True
                if self._prune_expired_locked():
                    dirty = True
                if self._enforce_max_sessions_locked():
                    dirty = True
                if dirty:
                    self._save_sessions_locked()
        except Exception:
            log.exception("Failed to load sessions")

    def get_session(self, token: str) -> Optional[DeviceSession]:
        """Retrieve data required to get session."""
        # Read-path helpers should avoid mutating shared state where possible.
        with self._lock:
            s = self.sessions.get(token)
            if not s:
                return None
            if self._is_expired(s):
                try:
                    self.sessions.pop(token, None)
                    self._save_sessions_locked()
                except Exception:
                    pass
                return None
            self._touch(s)
            return s

    def register_socket(self, token: str, ws: WebSocket) -> None:
        """Register socket."""
        with self._lock:
            if token in self.sessions:
                self.sessions[token].websocket = ws
                self.sessions[token].last_ws_seen_ts = time.time()
                self._touch(self.sessions[token])

    def unregister_socket(self, token: str, ws: Optional[WebSocket] = None) -> None:
        """Unregister socket."""
        with self._lock:
            if token in self.sessions:
                cur = self.sessions[token].websocket
                if ws is not None and cur is not ws:
                    return
                self.sessions[token].websocket = None
                self.sessions[token].last_ws_seen_ts = time.time()
                self._touch(self.sessions[token])

    def delete_session(self, token: str) -> bool:
        """Delete session."""
        with self._lock:
            if token not in self.sessions:
                return False
            try:
                self.sessions.pop(token, None)
                self._save_sessions_locked()
                return True
            except Exception:
                log.exception("Failed to delete session")
                return False

    def update_settings(self, token: str, patch: Dict[str, Any]) -> bool:
        """Update settings."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        with self._lock:
            s = self.sessions.get(token)
            if not s:
                return False
            if not isinstance(patch, dict):
                return False
            for k, v in patch.items():
                if v is None:
                    try:
                        s.settings.pop(k, None)
                    except Exception:
                        pass
                else:
                    s.settings[k] = v
            self._touch(s)
            self._save_sessions_locked()
            return True

    def get_all_devices(self):
        """Retrieve data required to get all devices."""
        # Read-path helpers should avoid mutating shared state where possible.
        with self._lock:
            out = []
            now = time.time()
            try:
                grace_s = max(0.0, float(getattr(config, "DEVICE_ONLINE_GRACE_S", 0.0) or 0.0))
            except Exception:
                grace_s = 0.0
            for t, s in self.sessions.items():
                try:
                    last_ws = float(getattr(s, "last_ws_seen_ts", 0.0) or 0.0)
                except Exception:
                    last_ws = 0.0
                online = bool(s.websocket) or (grace_s > 0.0 and (now - last_ws) <= grace_s)
                out.append(
                    {
                        "name": s.device_name,
                        "ip": s.ip,
                        "token": t,
                        "online": bool(online),
                        "settings": s.settings,
                        "created_ts": float(getattr(s, "created_ts", 0.0) or 0.0),
                        "last_seen_ts": float(getattr(s, "last_seen_ts", 0.0) or 0.0),
                    }
                )
            return out


