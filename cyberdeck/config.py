import os
import socket
import sys
import time
import uuid
from typing import List


VERSION = "v1.3.0"
PROTOCOL_VERSION = int(os.environ.get("CYBERDECK_PROTOCOL_VERSION", "2"))
MIN_SUPPORTED_PROTOCOL_VERSION = int(os.environ.get("CYBERDECK_MIN_PROTOCOL_VERSION", "1"))


def _is_packaged_runtime() -> bool:
    """Return True when running from a packaged executable (Nuitka/PyInstaller)."""
    if bool(getattr(sys, "frozen", False)):
        return True
    if "__compiled__" in globals():
        return True
    try:
        main_mod = sys.modules.get("__main__")
        if main_mod is not None and hasattr(main_mod, "__compiled__"):
            return True
    except Exception:
        pass
    try:
        exe_path = str(getattr(sys, "executable", "") or "")
        exe_name = os.path.basename(exe_path).strip().lower()
        python_like = {"python", "python3", "python.exe", "pythonw.exe", "py.exe", "pypy", "pypy3"}
        if exe_name and (exe_name not in python_like) and ("python" not in exe_name) and ("pypy" not in exe_name):
            return True
    except Exception:
        pass
    return False


def _csv_list(raw: str) -> List[str]:
    """Parse a comma-separated string into normalized non-empty values."""
    out: List[str] = []
    for x in str(raw or "").split(","):
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
    return out

HOST = "0.0.0.0"
PORT = int(os.environ.get("CYBERDECK_PORT", "8080"))
PORT_AUTO = os.environ.get("CYBERDECK_PORT_AUTO", "1") == "1"
UDP_PORT = int(os.environ.get("CYBERDECK_UDP_PORT", "5555"))
MDNS_ENABLED = os.environ.get("CYBERDECK_MDNS", "1") == "1"

_IS_LINUX_WAYLAND = (
    os.name != "nt"
    and (
        (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower() == "wayland"
        or bool(os.environ.get("WAYLAND_DISPLAY"))
    )
)
_CURSOR_STREAM_DEFAULT = "0" if _IS_LINUX_WAYLAND else "1"
CURSOR_STREAM = int(os.environ.get("CYBERDECK_CURSOR_STREAM", _CURSOR_STREAM_DEFAULT)) == 1
CURSOR_STREAM_FPS = int(os.environ.get("CYBERDECK_CURSOR_FPS", "30"))
STREAM_MONITOR = int(os.environ.get("CYBERDECK_STREAM_MONITOR", "1"))
WS_HEARTBEAT_INTERVAL_S = int(os.environ.get("CYBERDECK_WS_HEARTBEAT_INTERVAL_S", "15"))
WS_HEARTBEAT_TIMEOUT_S = int(os.environ.get("CYBERDECK_WS_HEARTBEAT_TIMEOUT_S", "45"))
VERBOSE_STREAM_LOG = os.environ.get("CYBERDECK_VERBOSE_STREAM_LOG", "1") == "1"
VERBOSE_WS_LOG = os.environ.get("CYBERDECK_VERBOSE_WS_LOG", "1") == "1"
VERBOSE_HTTP_LOG = os.environ.get("CYBERDECK_VERBOSE_HTTP_LOG", "1") == "1"
CORS_ORIGINS = _csv_list(os.environ.get("CYBERDECK_CORS_ORIGINS", "*")) or ["*"]
CORS_ALLOW_CREDENTIALS = os.environ.get("CYBERDECK_CORS_ALLOW_CREDENTIALS", "0") == "1"
if "*" in CORS_ORIGINS:
    CORS_ALLOW_CREDENTIALS = False
ALLOW_QUERY_TOKEN = os.environ.get("CYBERDECK_ALLOW_QUERY_TOKEN", "0") == "1"

DEBUG = os.environ.get("CYBERDECK_DEBUG", "0") == "1"
CONSOLE_LOG = os.environ.get("CYBERDECK_CONSOLE", "0") == "1"
LOG_ENABLED = os.environ.get("CYBERDECK_LOG", "0") == "1" or CONSOLE_LOG

TLS_CERT = os.environ.get("CYBERDECK_TLS_CERT", "")
TLS_KEY = os.environ.get("CYBERDECK_TLS_KEY", "")
TLS_ENABLED = os.environ.get("CYBERDECK_TLS", "0") == "1" and bool(TLS_CERT and TLS_KEY)
SCHEME = "https" if TLS_ENABLED else "http"

SESSION_TTL_S = int(os.environ.get("CYBERDECK_SESSION_TTL_S", "0"))
SESSION_IDLE_TTL_S = int(os.environ.get("CYBERDECK_SESSION_IDLE_TTL_S", "0"))
MAX_SESSIONS = int(os.environ.get("CYBERDECK_MAX_SESSIONS", "0"))

PIN_WINDOW_S = int(os.environ.get("CYBERDECK_PIN_WINDOW_S", "60"))
PIN_MAX_FAILS = int(os.environ.get("CYBERDECK_PIN_MAX_FAILS", "8"))
PIN_BLOCK_S = int(os.environ.get("CYBERDECK_PIN_BLOCK_S", "300"))
PIN_STATE_STALE_S = int(os.environ.get("CYBERDECK_PIN_STATE_STALE_S", "7200"))
PIN_STATE_MAX_IPS = int(os.environ.get("CYBERDECK_PIN_STATE_MAX_IPS", "4096"))

PAIRING_TTL_S = int(os.environ.get("CYBERDECK_PAIRING_TTL_S", "0"))
QR_TOKEN_TTL_S = int(os.environ.get("CYBERDECK_QR_TOKEN_TTL_S", "120"))
UPLOAD_MAX_BYTES = int(os.environ.get("CYBERDECK_UPLOAD_MAX_BYTES", "0"))
UPLOAD_ALLOWED_EXT = [x.lower() for x in _csv_list(os.environ.get("CYBERDECK_UPLOAD_ALLOWED_EXT", ""))]
TRANSFER_SCHEME = str(os.environ.get("CYBERDECK_TRANSFER_SCHEME", "auto") or "auto").strip().lower()

RUNTIME_PACKAGED = _is_packaged_runtime()

if RUNTIME_PACKAGED:
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # РєРѕСЂРµРЅСЊ СЂРµРїРѕР·РёС‚РѕСЂРёСЏ (СЂРѕРґРёС‚РµР»СЊСЃРєР°СЏ РїР°РїРєР° РїР°РєРµС‚Р°)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MODULE_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RESOURCE_DIR_ENV = str(os.environ.get("CYBERDECK_RESOURCE_DIR", "") or "").strip()
RESOURCE_DIR = _RESOURCE_DIR_ENV or _MODULE_BASE_DIR
if not os.path.exists(os.path.join(RESOURCE_DIR, "static")):
    RESOURCE_DIR = BASE_DIR

DATA_DIR = os.path.abspath(str(os.environ.get("CYBERDECK_DATA_DIR", BASE_DIR) or BASE_DIR))
_FILES_DIR_ENV = str(os.environ.get("CYBERDECK_FILES_DIR", "") or "").strip()
FILES_DIR = _FILES_DIR_ENV or os.path.join(os.path.expanduser("~"), "Downloads")
SESSION_FILE = os.path.join(DATA_DIR, "cyberdeck_sessions.json")
STATIC_DIR = os.path.join(RESOURCE_DIR, "static")
LOG_FILE = os.path.join(DATA_DIR, "cyberdeck.log")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR, exist_ok=True)

_PAIRING_CODE_ENV = str(os.environ.get("CYBERDECK_PAIRING_CODE", "") or "").strip()
PAIRING_CODE = (_PAIRING_CODE_ENV[:4] if _PAIRING_CODE_ENV else str(uuid.uuid4().int)[:4])
PAIRING_EXPIRES_AT = (time.time() + PAIRING_TTL_S) if PAIRING_TTL_S > 0 else None
SERVER_ID = str(uuid.uuid4())[:8]
if os.name == "nt":
    HOSTNAME = os.environ.get("COMPUTERNAME") or "CyberDeck PC"
else:
    HOSTNAME = os.environ.get("HOSTNAME") or socket.gethostname() or "CyberDeck PC"


def reload_from_env() -> None:
    """Reload runtime configuration from environment variables."""
    global PORT, PORT_AUTO, DEBUG, CONSOLE_LOG, LOG_ENABLED
    global SESSION_TTL_S, SESSION_IDLE_TTL_S, MAX_SESSIONS
    global PIN_WINDOW_S, PIN_MAX_FAILS, PIN_BLOCK_S
    global PAIRING_TTL_S, PAIRING_EXPIRES_AT, PAIRING_CODE
    global MDNS_ENABLED, STREAM_MONITOR
    global PROTOCOL_VERSION, MIN_SUPPORTED_PROTOCOL_VERSION
    global WS_HEARTBEAT_INTERVAL_S, WS_HEARTBEAT_TIMEOUT_S
    global VERBOSE_STREAM_LOG, VERBOSE_WS_LOG, VERBOSE_HTTP_LOG
    global CORS_ORIGINS, CORS_ALLOW_CREDENTIALS
    global ALLOW_QUERY_TOKEN
    global TLS_CERT, TLS_KEY, TLS_ENABLED, SCHEME
    global PIN_STATE_STALE_S, PIN_STATE_MAX_IPS
    global QR_TOKEN_TTL_S, UPLOAD_MAX_BYTES, UPLOAD_ALLOWED_EXT, TRANSFER_SCHEME

    PORT = int(os.environ.get("CYBERDECK_PORT", str(PORT)))
    PORT_AUTO = os.environ.get("CYBERDECK_PORT_AUTO", "1") == "1"
    MDNS_ENABLED = os.environ.get("CYBERDECK_MDNS", "1") == "1"

    DEBUG = os.environ.get("CYBERDECK_DEBUG", "0") == "1"
    CONSOLE_LOG = os.environ.get("CYBERDECK_CONSOLE", "0") == "1"
    LOG_ENABLED = os.environ.get("CYBERDECK_LOG", "0") == "1" or CONSOLE_LOG

    SESSION_TTL_S = int(os.environ.get("CYBERDECK_SESSION_TTL_S", str(SESSION_TTL_S)))
    SESSION_IDLE_TTL_S = int(os.environ.get("CYBERDECK_SESSION_IDLE_TTL_S", str(SESSION_IDLE_TTL_S)))
    MAX_SESSIONS = int(os.environ.get("CYBERDECK_MAX_SESSIONS", str(MAX_SESSIONS)))

    PIN_WINDOW_S = int(os.environ.get("CYBERDECK_PIN_WINDOW_S", str(PIN_WINDOW_S)))
    PIN_MAX_FAILS = int(os.environ.get("CYBERDECK_PIN_MAX_FAILS", str(PIN_MAX_FAILS)))
    PIN_BLOCK_S = int(os.environ.get("CYBERDECK_PIN_BLOCK_S", str(PIN_BLOCK_S)))

    STREAM_MONITOR = int(os.environ.get("CYBERDECK_STREAM_MONITOR", str(STREAM_MONITOR)))
    PROTOCOL_VERSION = int(os.environ.get("CYBERDECK_PROTOCOL_VERSION", str(PROTOCOL_VERSION)))
    MIN_SUPPORTED_PROTOCOL_VERSION = int(
        os.environ.get("CYBERDECK_MIN_PROTOCOL_VERSION", str(MIN_SUPPORTED_PROTOCOL_VERSION))
    )
    WS_HEARTBEAT_INTERVAL_S = int(
        os.environ.get("CYBERDECK_WS_HEARTBEAT_INTERVAL_S", str(WS_HEARTBEAT_INTERVAL_S))
    )
    WS_HEARTBEAT_TIMEOUT_S = int(
        os.environ.get("CYBERDECK_WS_HEARTBEAT_TIMEOUT_S", str(WS_HEARTBEAT_TIMEOUT_S))
    )
    VERBOSE_STREAM_LOG = os.environ.get("CYBERDECK_VERBOSE_STREAM_LOG", "1") == "1"
    VERBOSE_WS_LOG = os.environ.get("CYBERDECK_VERBOSE_WS_LOG", "1") == "1"
    VERBOSE_HTTP_LOG = os.environ.get("CYBERDECK_VERBOSE_HTTP_LOG", "1") == "1"
    CORS_ORIGINS = _csv_list(os.environ.get("CYBERDECK_CORS_ORIGINS", ",".join(CORS_ORIGINS))) or ["*"]
    CORS_ALLOW_CREDENTIALS = os.environ.get("CYBERDECK_CORS_ALLOW_CREDENTIALS", "0") == "1"
    if "*" in CORS_ORIGINS:
        CORS_ALLOW_CREDENTIALS = False
    ALLOW_QUERY_TOKEN = os.environ.get("CYBERDECK_ALLOW_QUERY_TOKEN", "0") == "1"

    TLS_CERT = os.environ.get("CYBERDECK_TLS_CERT", TLS_CERT)
    TLS_KEY = os.environ.get("CYBERDECK_TLS_KEY", TLS_KEY)
    TLS_ENABLED = os.environ.get("CYBERDECK_TLS", "0") == "1" and bool(TLS_CERT and TLS_KEY)
    SCHEME = "https" if TLS_ENABLED else "http"

    PAIRING_TTL_S = int(os.environ.get("CYBERDECK_PAIRING_TTL_S", str(PAIRING_TTL_S)))
    PAIRING_EXPIRES_AT = (time.time() + PAIRING_TTL_S) if PAIRING_TTL_S > 0 else None
    QR_TOKEN_TTL_S = int(os.environ.get("CYBERDECK_QR_TOKEN_TTL_S", str(QR_TOKEN_TTL_S)))
    UPLOAD_MAX_BYTES = int(os.environ.get("CYBERDECK_UPLOAD_MAX_BYTES", str(UPLOAD_MAX_BYTES)))
    UPLOAD_ALLOWED_EXT = [
        x.lower() for x in _csv_list(os.environ.get("CYBERDECK_UPLOAD_ALLOWED_EXT", ",".join(UPLOAD_ALLOWED_EXT)))
    ]
    TRANSFER_SCHEME = str(os.environ.get("CYBERDECK_TRANSFER_SCHEME", TRANSFER_SCHEME or "auto") or "auto").strip().lower()
    PIN_STATE_STALE_S = int(os.environ.get("CYBERDECK_PIN_STATE_STALE_S", str(PIN_STATE_STALE_S)))
    PIN_STATE_MAX_IPS = int(os.environ.get("CYBERDECK_PIN_STATE_MAX_IPS", str(PIN_STATE_MAX_IPS)))

    p = str(os.environ.get("CYBERDECK_PAIRING_CODE", "") or "").strip()
    if p:
        PAIRING_CODE = p[:4]
