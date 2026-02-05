import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import WebSocket

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


class DeviceManager:
    def __init__(self) -> None:
        self.sessions: Dict[str, DeviceSession] = {}

    def _touch(self, s: DeviceSession) -> None:
        try:
            s.last_seen_ts = time.time()
        except Exception:
            pass

    def _is_expired(self, s: DeviceSession, now: Optional[float] = None) -> bool:
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

    def _prune_expired(self) -> None:
        now = time.time()
        expired = [t for t, s in self.sessions.items() if self._is_expired(s, now=now)]
        if not expired:
            return
        for t in expired:
            try:
                self.sessions.pop(t, None)
            except Exception:
                pass
        self.save_sessions()

    def _enforce_max_sessions(self) -> None:
        try:
            max_s = int(config.MAX_SESSIONS or 0)
        except Exception:
            max_s = 0
        if max_s <= 0:
            return
        if len(self.sessions) <= max_s:
            return

        items = list(self.sessions.items())
        items.sort(key=lambda kv: float(getattr(kv[1], "last_seen_ts", 0.0) or 0.0))
        to_evict = max(0, len(items) - max_s)
        if to_evict <= 0:
            return
        for token, _s in items[:to_evict]:
            try:
                self.sessions.pop(token, None)
            except Exception:
                pass
        self.save_sessions()

    def authorize(self, device_id: str, name: str, ip: str) -> str:
        self._prune_expired()
        for t, s in self.sessions.items():
            if s.device_id == device_id:
                s.ip = ip
                s.device_name = name
                self._touch(s)
                self.save_sessions()
                return t

        self._enforce_max_sessions()
        s = DeviceSession(device_id=device_id, device_name=name, ip=ip)
        self.sessions[s.token] = s
        self.save_sessions()
        return s.token

    def save_sessions(self) -> None:
        try:
            data = {
                t: {
                    "device_id": s.device_id,
                    "device_name": s.device_name,
                    "ip": s.ip,
                    "settings": s.settings,
                    "created_ts": float(getattr(s, "created_ts", 0.0) or 0.0),
                    "last_seen_ts": float(getattr(s, "last_seen_ts", 0.0) or 0.0),
                }
                for t, s in self.sessions.items()
            }
            with open(config.SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            log.exception("Failed to save sessions")

    def load_sessions(self) -> None:
        try:
            if os.path.exists(config.SESSION_FILE):
                with open(config.SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for t, i in data.items():
                        self.sessions[t] = DeviceSession(
                            device_id=i.get("device_id"),
                            device_name=i.get("device_name"),
                            ip=i.get("ip"),
                            token=t,
                            settings=i.get("settings") or {},
                            created_ts=float(i.get("created_ts") or time.time()),
                            last_seen_ts=float(i.get("last_seen_ts") or time.time()),
                        )
            self._prune_expired()
            self._enforce_max_sessions()
        except Exception:
            log.exception("Failed to load sessions")

    def get_session(self, token: str) -> Optional[DeviceSession]:
        s = self.sessions.get(token)
        if not s:
            return None
        if self._is_expired(s):
            try:
                self.sessions.pop(token, None)
                self.save_sessions()
            except Exception:
                pass
            return None
        self._touch(s)
        return s

    def register_socket(self, token: str, ws: WebSocket) -> None:
        if token in self.sessions:
            self.sessions[token].websocket = ws
            self._touch(self.sessions[token])

    def unregister_socket(self, token: str) -> None:
        if token in self.sessions:
            self.sessions[token].websocket = None
            self._touch(self.sessions[token])

    def delete_session(self, token: str) -> bool:
        if token not in self.sessions:
            return False
        try:
            self.sessions.pop(token, None)
            self.save_sessions()
            return True
        except Exception:
            log.exception("Failed to delete session")
            return False

    def update_settings(self, token: str, patch: Dict[str, Any]) -> bool:
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
        self.save_sessions()
        return True

    def get_all_devices(self):
        out = []
        for t, s in self.sessions.items():
            out.append(
                {
                    "name": s.device_name,
                    "ip": s.ip,
                    "token": t,
                    "online": bool(s.websocket),
                    "settings": s.settings,
                    "created_ts": float(getattr(s, "created_ts", 0.0) or 0.0),
                    "last_seen_ts": float(getattr(s, "last_seen_ts", 0.0) or 0.0),
                }
            )
        return out
